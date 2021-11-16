{
  pkgs ? import <nixpkgs> {},
  path
}:
let
  inherit (builtins) replaceStrings getFlake fetchTarball;
  inherit (pkgs) fetchzip;
  flake-compat = import (fetchTarball {
    url = "https://github.com/edolstra/flake-compat/archive/4112a081eff4b4d91d2db383c301780ee3c17b2b.tar.gz";
    sha256 = "0jm6nzb83wa6ai17ly9fzpqc40wg1viib8klq8lby54agpl213w5";
  });

  flake = flake-compat { src = path; };
in pkgs.symlinkJoin {
  name = "docs";
  paths = with flake.defaultNix.htmlDocs; [ nixpkgsManual nixosManual ];
}
