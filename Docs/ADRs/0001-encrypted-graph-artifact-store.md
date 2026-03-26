# ADR 0001: Local Encrypted Store for Microsoft Graph Artifacts

- Status: Accepted
- Date: 2026-03-26

## Context

This repo is moving beyond direct Microsoft Graph actions and will likely need a local store for fetched or generated artifacts such as:

- mail message payloads
- attachments
- calendar exports
- chat payloads
- notes
- file metadata and downloaded file content

The store needs to optimize for three things at once:

- fast local reads and writes
- strong at-rest protection
- minimal user friction after the user has already signed into their OS session

Working assumption for this ADR:

- the store is local to the user machine running these scripts
- the primary environment is desktop or laptop automation
- cross-device sync is out of scope for the first implementation

## Decision Drivers

- secure storage of Graph artifact contents at rest
- minimal prompting and setup burden for users
- good performance for both small metadata and larger downloaded blobs
- compatibility with Python-based local tooling
- straightforward backup, rotation, and recovery story
- low packaging and installation friction for the repo

## Options Considered

### Option 1: SQLCipher-encrypted SQLite for everything

Store metadata and artifact bodies in a single encrypted SQLCipher database.

Pros:

- mature full-database encryption model
- strong transactional behavior
- simple single-store mental model
- good fit when the stored data is mostly structured records or small to medium blobs

Cons:

- adds packaging and integration complexity compared with Python's built-in `sqlite3`
- official SQLCipher docs note that Community and Commercial performance differ, and the optimized packages are not the default open source path
- SQLite's own blob guidance suggests that separate files become more attractive as blobs grow larger than about 100 KB
- if WAL mode is used, SQLite creates companion `-wal` and `-shm` files that must be managed alongside the database

Assessment:

- viable, but heavier than needed for the first local artifact store in this repo

### Option 2: Hybrid store with SQLite index plus encrypted artifact files

Use SQLite for indexing and operational metadata, and store artifact payloads as individually encrypted files on disk.

Pros:

- keeps indexing and lookups fast with standard SQLite
- handles large Graph artifacts better than forcing everything into one database file
- allows clean separation between searchable metadata and ciphertext payloads
- works well with native OS secret stores because only a small master key or wrapping key must be stored there
- avoids taking on SQLCipher packaging as a prerequisite for the repo

Cons:

- more implementation work than a single database
- requires careful discipline around which metadata remains indexable versus encrypted
- needs explicit garbage collection and consistency checks between the index and artifact files

Assessment:

- best fit for this repo's current constraints

### Option 3: Rely only on OS disk encryption such as FileVault or BitLocker

Keep app artifacts in plaintext and depend on full-disk encryption.

Pros:

- nearly zero application complexity
- seamless to end users when their machine is already configured securely

Cons:

- does not provide app-level protection once the user is logged in
- copied files, backups, and exported artifacts may leave the encrypted volume boundary
- does not give the repo a portable or auditable security model of its own

Assessment:

- acceptable as a baseline platform control, but not sufficient as the primary design

## Decision

Adopt Option 2 as the default architecture for the first encrypted artifact store:

- a local SQLite index for operational metadata
- a sibling artifact directory containing encrypted payload files
- a randomly generated master key or key-encryption key stored in the OS credential store
- per-artifact encryption keys wrapped by that master key
- authenticated encryption for each artifact payload

Recommended implementation direction:

1. Store only a small secret in the OS credential store.
   On macOS, use Keychain-backed storage.
   On Windows, use DPAPI or Credential Locker for the wrapped key material.
   On Linux, use Secret Service when available.

2. Keep the local index in SQLite.
   The index should hold only the minimum fields required for lookup and integrity operations, such as:
   - artifact ID
   - account or tenant fingerprint
   - artifact type
   - timestamps
   - ciphertext path
   - size
   - content hash
   - sync state
   Sensitive metadata that is not needed for indexing should be stored encrypted.

3. Store artifact bodies as encrypted files.
   This is the better default for mixed Microsoft Graph workloads because some artifacts are small JSON payloads while others are large files or attachments.

4. Use AEAD encryption for each artifact.
   Prefer XChaCha20-Poly1305 for file payloads. For large or streamed artifacts, use `secretstream` so the implementation does not need to hold the entire plaintext in memory.

5. Bind integrity to metadata.
   Include stable associated data such as schema version, artifact ID, artifact type, and account fingerprint so ciphertext cannot be replayed into the wrong logical record.

6. Design the storage layer behind an interface.
   If the repo later needs a single-file encrypted backend, SQLCipher can be added as an alternate implementation without changing higher-level scripts.

Current starter implementation status:

- implemented as a shared local storage library under `scripts/lib/storage/`
- uses SQLite for the index and encrypted per-artifact files on disk
- uses the OS keyring for the long-lived master key
- currently uses PyNaCl `Aead` for per-artifact authenticated encryption
- keeps the interface open for a future streamed-file implementation

## Why This Is The Recommendation

This option is the best balance of speed, security, and user experience for this repo.

It is fast because SQLite is efficient for local indexing, and official SQLite guidance shows that small blobs often perform well in-database while larger blobs trend toward separate-file storage. Microsoft Graph artifacts are a mix of both, which is exactly where a hybrid model makes sense.

It is secure because artifact contents are encrypted by the application, not only by the underlying disk, and the long-lived secret can be delegated to the operating system's secure credential store instead of asking the user to manage a separate passphrase every time.

It is seamless because the user experience lines up with the normal desktop login model. The app only needs the OS secret store for a small piece of key material; it should not try to place large payloads into the keychain or credential locker.

## Implementation Notes

- Keep the store in a gitignored repo-local directory, for example `.graph_store/`.
- Use atomic writes: write to a temp file, fsync, then rename.
- Add periodic integrity checks to detect index/file drift.
- Support key rotation by rewrapping per-artifact keys rather than forcing immediate full re-encryption.
- Treat debug logs and session logs as separate concerns; they must never store decrypted artifact content by default.

## Consequences

Positive:

- low end-user friction
- strong at-rest protection beyond disk encryption alone
- efficient handling of mixed-size Graph artifacts
- no hard dependency on SQLCipher for the initial implementation

Negative:

- more code than a single encrypted database
- metadata classification must be deliberate
- Linux secret-store behavior can vary more than macOS or Windows

## Research Notes

- SQLite reports that storing blobs directly in the database is often faster for small blobs, while separate files become faster for larger blobs.
- SQLite WAL mode improves concurrency, but it also creates `-wal` and `-shm` companion files that application designs need to account for.
- SQLCipher provides full-database encryption and documents relatively low overhead for many workloads, but its official materials also distinguish between Community and optimized commercial distributions.
- Windows Credential Locker explicitly says it should be used for passwords rather than larger data blobs.
- The Secret Service specification states that lookup attributes are not treated as secret material and may not be encrypted, which is an important design constraint.

## Sources

- [Internal Versus External BLOBs in SQLite](https://www.sqlite.org/intern-v-extern-blob.html)
- [35% Faster Than The Filesystem](https://www.sqlite.org/fasterthanfs.html)
- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html)
- [SQLCipher Overview](https://www.zetetic.net/sqlcipher/)
- [SQLCipher Performance Optimization](https://www.zetetic.net/sqlcipher/performance/)
- [SQLCipher API](https://www.zetetic.net/sqlcipher/sqlcipher-api/)
- [Python keyring documentation](https://keyring.readthedocs.io/en/stable/)
- [Credential Locker for Windows apps](https://learn.microsoft.com/en-us/windows/apps/develop/security/credential-locker)
- [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
- [Apple Cryptographic Services Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/cryptoservices/Introduction/Introduction.html)
- [Managing Keys, Certificates, and Passwords](https://developer.apple.com/library/archive/documentation/Security/Conceptual/cryptoservices/KeyManagementAPIs/KeyManagementAPIs.html)
- [Secret Service API](https://specifications.freedesktop.org/secret-service-spec/latest-single)
- [XChaCha20-Poly1305 construction](https://libsodium.gitbook.io/doc/secret-key_cryptography/aead/chacha20-poly1305/xchacha20-poly1305_construction)
- [Encrypted streams and file encryption](https://libsodium.gitbook.io/doc/secret-key_cryptography/secretstream)
- [PyNaCl secret key encryption](https://pynacl.readthedocs.io/en/latest/secret/)
