{
  description = "QDash development shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    # Pinned so the Nix shell runs the same betterleaks release as
    # .devcontainer/Dockerfile (BETTERLEAKS_VERSION); newer releases add rules
    # that flag the repository's fixed sample credentials.
    nixpkgs-betterleaks.url = "github:NixOS/nixpkgs/f3a6890d30cfd033e21cc4714461c5fd327eb9ea";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-betterleaks,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        betterleaks = nixpkgs-betterleaks.legacyPackages.${system}.betterleaks;

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
            lychee
            lsof
            nodejs_24
            pkg-config
            postgresql_14
            python311
            trufflehog
            uv
          ]
          ++ [ betterleaks ];

          env = {
            UV_LINK_MODE = "copy";
            UV_PYTHON = "${pkgs.python311}/bin/python";
            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath runtimeLibs;
          };

          shellHook = ''
            export PATH="$HOME/.local/bin:$PWD/ui/node_modules/.bin:$PATH:$PWD/.venv/bin"

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
