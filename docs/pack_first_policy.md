# Pack First Policy

For a Strong Model driving RepoScout: prefer `reposcout pack` over repeated
individual reads. This does not summarize or judge Evidence -- it only
removes duplicate/overlapping/adjacent reads of the same source before they
reach model context (see `src/reposcout/pack.py`).

1. When multiple sources or ranges are needed, call `reposcout pack` before
   issuing individual reads.
2. Do not re-read a path/range already present in a Pack.
3. Avoid re-reading the same path + range + content hash.
4. Re-reading is permitted only when:
   - the Pack does not cover the needed range,
   - the source has changed since the Pack was built,
   - Evidence is contradictory, or
   - a final decision requires close reading of a specific, already-narrowed
     range.
5. When re-reading is necessary, fetch only the missing range -- not the
   whole file again.
6. Stop exploring once `stop_conditions` (Investigation Contract) are met.
