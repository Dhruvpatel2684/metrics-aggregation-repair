import json
import os
import glob
import logging

logger = logging.getLogger("metrics.ingest")

COLLECTORS_DIR = os.path.join(os.path.dirname(__file__), "collectors")


def load_samples():
    """Load all metric samples from collector JSONL files."""
    pattern = os.path.join(COLLECTORS_DIR, "collector_*.jsonl")
    files = sorted(glob.glob(pattern))
    if not files:
        logger.error("no collector files found in %s", COLLECTORS_DIR)
        return []

    samples = []
    for fpath in files:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sample = json.loads(line)
                samples.append(sample)

    logger.info("loaded %d samples from %d collectors", len(samples), len(files))
    return samples
