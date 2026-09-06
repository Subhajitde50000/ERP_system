# Cloudflare R2 Storage

Cloudflare R2 is the primary production storage backend. Uploads, downloads,
presigned links, and deletes use R2 through its S3-compatible HTTPS API. The
application keeps a separate S3 configuration block so a deployer can move to
Amazon S3 or another S3-compatible service without code changes.

## Primary R2 configuration

Create an R2 bucket and an API token limited to **Object Read & Write** for
that bucket. In the deployment environment set:

```bash
STORAGE_BACKEND=r2
R2_BUCKET=erp-media-production
R2_ENDPOINT_URL=https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
R2_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
R2_KEY_PREFIX=erp/
```

`R2_ENDPOINT_URL` must contain the Cloudflare account ID, not the public custom
domain. R2 uses the `auto` region; the application supplies that automatically.
Do not commit the access key or secret.

The backend validates all four required R2 values at application startup. This
prevents a deployment from silently storing production uploads on local disk.

## Switching a deployment to S3

Keep the `S3_*` variables in the environment. To use S3 instead of R2, change
only the backend selector and supply the S3 values:

```bash
STORAGE_BACKEND=s3
S3_BUCKET=erp-media-production
S3_REGION=ap-south-1
S3_ACCESS_KEY_ID=<AWS_ACCESS_KEY_ID>
S3_SECRET_ACCESS_KEY=<AWS_SECRET_ACCESS_KEY>
S3_KEY_PREFIX=erp/
S3_FORCE_PATH_STYLE=false
```

`S3_ENDPOINT_URL` is optional for AWS S3 and can be used for MinIO or another
S3-compatible provider. IAM-role credentials may be used instead of the S3 key
variables on AWS.

## Local development

For a local-only development environment, use `STORAGE_BACKEND=local`. Files
remain private under `UPLOAD_FILE_ROOT` and are served through the existing
signed file route, not by a public uploads directory.

## Operational notes

- Objects are stored under tenant-prefixed keys. `R2_KEY_PREFIX` and
  `S3_KEY_PREFIX` optionally add one additional bucket-wide prefix.
- Download links are presigned by the configured object-storage provider and
  expire according to `UPLOAD_SIGNED_URL_TTL_SECONDS`.
- Existing local uploads are not migrated automatically. Copy them to the R2
  bucket before relying on the new backend.
