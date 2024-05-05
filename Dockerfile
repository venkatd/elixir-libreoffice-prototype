# Find eligible builder and runner images on Docker Hub. We use Ubuntu/Debian
# instead of Alpine to avoid DNS resolution issues in production.
#
# https://hub.docker.com/r/hexpm/elixir/tags?page=1&name=ubuntu
# https://hub.docker.com/_/ubuntu?tab=tags
#
# This file is based on these images:
#
#   - https://hub.docker.com/r/hexpm/elixir/tags - for the build image
#   - https://hub.docker.com/_/debian?tab=tags&page=1&name=bullseye-20230612-slim - for the release image
#   - https://pkgs.org/ - resource for finding needed packages
#   - Ex: hexpm/elixir:1.15.6-erlang-26.1-debian-bullseye-20230612-slim
#
ARG ELIXIR_VERSION=1.16.2
ARG OTP_VERSION=26.2.4
ARG DEBIAN_VERSION=bookworm-20240423-slim

ARG BUILDER_IMAGE="hexpm/elixir:${ELIXIR_VERSION}-erlang-${OTP_VERSION}-debian-${DEBIAN_VERSION}"
ARG RUNNER_IMAGE="debian:${DEBIAN_VERSION}"

FROM ${BUILDER_IMAGE} as builder

# install build dependencies
RUN apt-get update -y && apt-get install -y build-essential git \
    && apt-get clean && rm -f /var/lib/apt/lists/*_*

# prepare build dir
WORKDIR /app

# install hex + rebar
RUN mix local.hex --force && \
    mix local.rebar --force

# set build ENV
ENV MIX_ENV="prod"

# install mix dependencies
COPY mix.exs mix.lock ./
RUN mix deps.get --only $MIX_ENV
RUN mkdir config

# copy compile-time config files before we compile dependencies
# to ensure any relevant config change will trigger the dependencies
# to be re-compiled.
COPY config/config.exs config/${MIX_ENV}.exs config/
RUN mix deps.compile

COPY priv priv

COPY lib lib

COPY assets assets

# compile assets
RUN mix assets.deploy

# Compile the release
RUN mix compile

# Changes to config/runtime.exs don't require recompiling the code
COPY config/runtime.exs config/

COPY rel rel
RUN mix release

# start a new build stage so that the final image will only contain
# the compiled release and other runtime necessities
FROM ${RUNNER_IMAGE}

RUN apt-get update -y && \
  apt-get install -y libstdc++6 openssl libncurses5 locales ca-certificates ffmpeg \
  && apt-get clean && rm -f /var/lib/apt/lists/*_*

RUN \
    # Install system dependencies required for the next instructions or debugging.
    # Note: tini is a helper for reaping zombie processes.
    apt-get update -qq &&\
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends curl gnupg tini python3 default-jre-headless &&\
    # Cleanup.
    # Note: the Debian image does automatically a clean after each install thanks to a hook.
    # Therefore, there is no need for apt-get clean.
    # See https://stackoverflow.com/a/24417119/3248473.
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN \
    # Install LibreOffice & unoconverter.
    echo "deb http://deb.debian.org/debian bookworm-backports main" >> /etc/apt/sources.list &&\
    apt-get update -qq &&\
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends -t bookworm-backports libreoffice &&\
    curl -Ls https://raw.githubusercontent.com/gotenberg/unoconverter/v0.0.1/unoconv -o /usr/bin/unoconverter &&\
    chmod +x /usr/bin/unoconverter &&\
    # unoconverter will look for the Python binary, which has to be at version 3.
    ln -s /usr/bin/python3 /usr/bin/python &&\
    # Verify installations.
    libreoffice --version &&\
    unoconverter --version &&\
    # Cleanup.
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set the locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen

ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

WORKDIR "/app"
RUN chown nobody /app

# set runner ENV
ENV MIX_ENV="prod"
ENV SHELL="/bin/bash"
ENV LIBREOFFICE_BIN_PATH /usr/lib/libreoffice/program/soffice.bin

# Only copy the final release from the build stage
COPY --from=builder --chown=nobody:root /app/_build/${MIX_ENV}/rel/thumbs ./

USER nobody

# If using an environment that doesn't automatically reap zombie processes, it is
# advised to add an init process such as tini via `apt-get install`
# above and adding an entrypoint. See https://github.com/krallin/tini for details
# ENTRYPOINT ["/tini", "--"]

CMD ["/app/bin/server"]
