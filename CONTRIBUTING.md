# Working together

Clone this repository rather than copying files between laptops. Verify setup on your platform before assuming hardware support.

Start a branch for each change:

```sh
git switch main
git pull --ff-only
git switch -c feature/your-change
```

Run replay tests before requesting hardware testing. Flight remains available through `--enable-flight`; never make flight automatic on startup. Preserve manual takeover, input expiration, low-battery handling, landing and neutral commands. New automation must use a tested command arbiter, not a second drone connection.

Before submitting:

```sh
python3 -m unittest discover -s tests
git diff --check
git add path/to/changed/file
git commit -m "Describe the resulting behavior"
git push -u origin HEAD
```

Open a pull request describing what changed, how it was tested, and whether hardware testing is still needed. Review flight-control changes before merging. Do not commit credentials, build outputs, environments, household video, or live telemetry logs.

After a pull request merges, everyone updates with:

```sh
git switch main
git pull --ff-only
```

The repository owner can invite collaborators in GitHub Settings → Collaborators. A public repository allows reading/cloning; it does not automatically grant write access. Anyone can also fork and submit a pull request.
