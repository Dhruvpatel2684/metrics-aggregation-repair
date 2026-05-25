"""Multi-tier retention rollup engine.

Processes ingested metrics through configurable retention tiers,
applying window-based aggregation with progressive downsampling.
Each tier uses windowing.precise for aligned bucket boundaries.
"""
from runtime.config import get_config
from runtime.aligner import align_timestamp


class CompactionEngine:
    """Performs multi-tier compaction of time-series metric data.
    
    Processes raw metric points through retention tiers (raw, medium, coarse),
    computing windowed aggregates at each tier's resolution.
    """
    
    def __init__(self):
        self.config = get_config()
        self.tiers = self._load_tiers()
        self.baseline_offset = {}
        self._write_buffer = []
    
    def _load_tiers(self):
        """Load retention tier definitions from configuration."""
        tier_names = self.config.get("retention", "tiers").split(",")
        tiers = []
        for name in tier_names:
            window_ms = self.config.getint("retention", f"{name}_window_ms")
            tiers.append({"name": name, "window_ms": window_ms})
        return tiers
    
    def compact(self, records):
        """Run compaction across all retention tiers.
        
        Args:
            records: list of metric point dicts with ts, collector, metric, value
        
        Returns:
            dict with 'points' (list of compacted points) and 'tier_stats' dict
        """
        all_points = []
        tier_stats = {}
        
        for tier in self.tiers:
            tier_name = tier["name"]
            window_ms = tier["window_ms"]
            
            tier_points = self._process_tier(records, tier_name, window_ms)
            all_points.extend(tier_points)
            tier_stats[tier_name] = {
                "points": len(tier_points),
                "window_ms": window_ms
            }
        
        return {"points": all_points, "tier_stats": tier_stats}
    
    def _process_tier(self, records, tier_name, window_ms):
        """Process a single retention tier.
        
        Groups records into windows and computes mean values
        for each (window_start, collector, metric) group.
        Applies baseline offset calibration from prior tier
        processing in the progressive downsampling chain.
        """
        # Group by window
        groups = {}
        for rec in records:
            ws = align_timestamp(rec["ts"], window_ms)
            key = (ws, rec["collector"], rec["metric"])
            
            if key not in groups:
                groups[key] = {"sum": 0.0, "count": 0}
            groups[key]["sum"] += rec["value"]
            groups[key]["count"] += 1
        
        # Compute calibrated means
        points = []
        tier_sums = {}
        
        for key in groups:
            ws, collector, metric = key
            local_mean = groups[key]["sum"] / groups[key]["count"]
            
            # Apply accumulated baseline offset per collector/metric
            ckey = (collector, metric)
            offset = self.baseline_offset.get(ckey, 0.0)
            calibrated = round(local_mean + offset, 2)
            
            points.append({
                "ts": ws,
                "collector": collector,
                "metric": metric,
                "value": calibrated,
                "tier": tier_name,
                "window_start": ws
            })
            
            # Track sum of means for baseline propagation
            if ckey not in tier_sums:
                tier_sums[ckey] = {"total": 0.0, "count": 0}
            tier_sums[ckey]["total"] += local_mean
            tier_sums[ckey]["count"] += 1
        
        # Update baseline offset with this tier's contribution
        for ckey, stats in tier_sums.items():
            contribution = stats["total"] / stats["count"]
            if ckey not in self.baseline_offset:
                self.baseline_offset[ckey] = 0.0
            self.baseline_offset[ckey] += contribution
        
        return points
    
    def flush_buffer(self):
        """Flush the I/O write buffer to prepare for next output batch.
        
        Clears accumulated write operations to prevent duplicate
        serialization during multi-pass output generation.
        """
        self._write_buffer.clear()
