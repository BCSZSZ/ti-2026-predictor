# Local data snapshots

Large immutable data snapshots are stored with Git LFS. They are recovery copies of ignored
runtime data, not the files read directly by the application.

After cloning, install Git LFS and restore a snapshot from the repository root:

```powershell
git lfs pull
7z x data/snapshots/<snapshot_id>/ti-data.7z -o.
```

Verify the archive SHA-256 against its adjacent `manifest.json` before extraction. A base snapshot
is never overwritten; later incremental collections receive a new snapshot directory so Git LFS
does not upload a replacement copy of the complete history.
