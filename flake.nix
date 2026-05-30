{
  description = "QDash development shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        runtimeLibs = with pkgs; [
          cairo
          glib
          gtk3
          hdf5
          postgresql_14
          stdenv.cc.cc.lib
          zlib
        ];
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            bashInteractive
            betterleaks
            bun
            curl
            docker-client
            docker-compose
            gcc
            git
            gnumake
            go-task
            jq
            lefthook
            lsof
            nodejs_20
            pkg-config
            postgresql_14
            python311
            trufflehog
            uv
          ];

          env = {
            UV_LINK_MODE = "copy";
            UV_PYTHON = "${pkgs.python311}/bin/python";
            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath runtimeLibs;
          };

          shellHook = ''
            export PATH="$PWD/ui/node_modules/.bin:$PATH:$PWD/.venv/bin"

            if [ ! -d .venv ]; then
              echo "Run: uv sync --locked --all-groups --all-packages"
            fi

            if [ ! -d ui/node_modules ]; then
              echo "Run: cd ui && bun install --frozen-lockfile"
            fi
          '';
        };
      }
    );
}
