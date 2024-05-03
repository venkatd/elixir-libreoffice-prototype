import Config

# We don't run a server during test. If one is required,
# you can enable the server option below.
config :thumbs, ThumbsWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}, port: 4002],
  secret_key_base: "2cMkPe5sJoQBRyAKLG+q7RxNCk0p+j44d7U5Pg9TcgvU8jFBV5eBlSKAM5eaSh1Q",
  server: false

# In test we don't send emails.
config :thumbs, Thumbs.Mailer, adapter: Swoosh.Adapters.Test

# Disable swoosh api client as it is only required for production adapters.
config :swoosh, :api_client, false

# Print only warnings and errors during test
config :logger, level: :warning

# Initialize plugs at runtime for faster test compilation
config :phoenix, :plug_init_mode, :runtime
