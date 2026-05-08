-- Password reset token columns
ALTER TABLE users.users
  ADD COLUMN IF NOT EXISTS password_reset_token     VARCHAR(128),
  ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_reset_token
  ON users.users (password_reset_token)
  WHERE password_reset_token IS NOT NULL;
