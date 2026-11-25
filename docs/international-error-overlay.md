# International Error-window hotfix (EN 1.2.2)

This hotfix updates only the English Steam international edition. The CN portable archive remains the v1.2.1 artifact, byte-for-byte unchanged.

## What changed

The local server enables `open_error_log`, a developer diagnostic window. On the pinned supported Steam private-client build, the adapter now turns off that window policy when the GM configuration is assigned or read. It does not globally replace logging, catch gameplay exceptions, or change ordinary failure/disconnection dialogs. Other GM configuration fields are preserved.

The policy is installed only in an isolated private client. No attachment to an official client is permitted, and unrecognized game builds still fail closed.

## Restart required

Exit the private game first, then start it again from the international launcher. An already running game has already loaded its adapter; copying new scripts does not hot-reload it. Save files do not need to be deleted or reimported.

## Scope and remaining compatibility limitations

The reported diagnostic window contained a missing `ShopPoolConfigure` entry. Missing configuration records and unsupported private-server features are a separate issue. This patch prevents the developer Error window from repeatedly interrupting play; it does not claim that every shop or game feature is now implemented.

## Verification

- 138 automated regression tests passed.
- Real isolated Steam IL2CPP setter/getter probes verified `open_error_log` changes from true to false while `open_gm` and `open_cs` remain unchanged.
- The CN executable was not rebuilt; its hash was checked unchanged.

Logs remain in the profile log directory. Please report any remaining interruption with its exact message rather than publishing private account data.
