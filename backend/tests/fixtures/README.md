Place small, non-sensitive PST fixtures here for local integration testing.

The repository does not include real PST files because Outlook exports commonly
contain private mail. The smoke script and unit tests run without fixtures.

Use `scripts\e2e-sample-pst.ps1` for the checked-in end-to-end path. It
downloads a small public PST fixture into an isolated temporary import folder.
