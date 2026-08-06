# Native Fantasy replay parser

This small Java 21+ helper reads only the final `CDOTA_DataRadiant` and `CDOTA_DataDire` entities
from a decompressed Dota replay. It emits structured JSON for the five TI 2026 Fantasy counters and
does not download replays, infer combat-log events or run a service.

Build:

```powershell
.\mvnw.cmd -q '-DskipTests' package
```

Run:

```powershell
java -jar target/ti-replay-parser.jar path/to/match.dem
```

The Python adapter owns immutable downloads, hashes, `as_of`, retries, timeouts and normalization.
It records the shaded JAR SHA-256 and fails closed if that artifact changes during one sync.
Clarity is used under its BSD-3-Clause license. The property-access pattern is informed by the
MIT-licensed OpenDota parser; see `THIRD_PARTY_NOTICES.md`.
