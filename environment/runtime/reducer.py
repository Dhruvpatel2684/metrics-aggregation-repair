"""Reducer processes events in batches and folds them into account balances."""

from configparser import ConfigParser


class Reducer:
    """Processes filtered events in batches to produce account balance state."""

    def __init__(self, config: ConfigParser):
        self._batch_size = config.getint("replay", "batch_size")
        self._balances = {}
        self._event_counts = {}
        self._last_updated = {}
        self._batch_count = 0
        self._snapshot_count = 0

    def process(self, events: list) -> dict:
        """Process all events in batches and return final account states."""
        for i in range(0, len(events), self._batch_size):
            batch = events[i:i + self._batch_size]
            self._process_batch(batch)
            self._batch_count += 1
        return self._balances

    def _process_batch(self, batch: list):
        """Process a single batch of events and fold into running totals.

        Each batch computes the updated balance for affected accounts by
        applying event deltas to the current known balance. The result
        for each account is the new authoritative balance after this batch.
        """
        batch_results = {}

        for event in batch:
            etype = event["type"]
            data = event["data"]

            if etype == "account_created":
                acct = data["account_id"]
                if acct not in self._balances:
                    self._balances[acct] = 0
                    self._event_counts[acct] = 0
                batch_results[acct] = self._balances.get(acct, 0)
                self._event_counts[acct] = self._event_counts.get(acct, 0) + 1
                self._last_updated[acct] = event["timestamp"]

            elif etype == "balance_updated":
                acct = data["account_id"]
                amount = data["amount"]
                direction = data["direction"]
                delta = amount if direction == "credit" else -amount
                current = batch_results.get(acct, self._balances.get(acct, 0))
                batch_results[acct] = current + delta
                self._event_counts[acct] = self._event_counts.get(acct, 0) + 1
                self._last_updated[acct] = event["timestamp"]

            elif etype == "transfer_completed":
                from_acct = data["from_account"]
                to_acct = data["to_account"]
                amount = data["amount"]
                from_current = batch_results.get(from_acct, self._balances.get(from_acct, 0))
                to_current = batch_results.get(to_acct, self._balances.get(to_acct, 0))
                batch_results[from_acct] = from_current - amount
                batch_results[to_acct] = to_current + amount
                self._event_counts[from_acct] = self._event_counts.get(from_acct, 0) + 1
                self._event_counts[to_acct] = self._event_counts.get(to_acct, 0) + 1
                self._last_updated[from_acct] = event["timestamp"]
                self._last_updated[to_acct] = event["timestamp"]

            elif etype == "snapshot_taken":
                acct = data.get("account_id")
                if acct:
                    balance = data.get("balance", data.get("validated_balance"))
                    if balance is not None:
                        batch_results[acct] = balance
                        self._snapshot_count += 1
                        self._event_counts[acct] = self._event_counts.get(acct, 0) + 1
                        self._last_updated[acct] = event["timestamp"]

        # Fold batch results into running totals
        for acct, batch_balance in batch_results.items():
            self._balances[acct] += batch_balance

    def get_balances(self) -> dict:
        """Return current account balances."""
        return self._balances.copy()

    def get_event_counts(self) -> dict:
        """Return per-account event counts."""
        return self._event_counts.copy()

    def get_last_updated(self) -> dict:
        """Return per-account last updated timestamps."""
        return self._last_updated.copy()

    def get_batch_count(self) -> int:
        """Return the number of batches processed."""
        return self._batch_count

    def get_snapshot_count(self) -> int:
        """Return the number of snapshot events applied."""
        return self._snapshot_count
