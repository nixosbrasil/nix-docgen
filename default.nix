{ pkgs ? import <nixpkgs> {}
, tarball_url
, tarball_sha256
, rev ? "master"
}:
let
  inherit (builtins) replaceStrings getFlake fetchTarball;
  inherit (pkgs) fetchzip;
  nixpkgs-path = fetchTarball {
    url = tarball_url;
    sha256 = tarball_sha256;
  };
  flake-compat = import (fetchTarball {
    url = "https://github.com/edolstra/flake-compat/archive/4112a081eff4b4d91d2db383c301780ee3c17b2b.tar.gz";
    sha256 = "0jm6nzb83wa6ai17ly9fzpqc40wg1viib8klq8lby54agpl213w5";
  });

  flake = flake-compat { src = nixpkgs-path; };
  zeal = import ./zeal {
    inherit pkgs rev;
    nixpkgs-flake = flake;
    nixpkgs-path = nixpkgs-path;
  };
in pkgs.stdenv.mkDerivation {
  name = "docs-${rev}";
  dontUnpack = true;
  installPhase = ''
    mkdir $out
    for f in ${flake.defaultNix.htmlDocs.nixpkgsManual}/share/doc/*; do
      ln -s "$f" $out/
    done
    for f in ${flake.defaultNix.htmlDocs.nixosManual}/share/doc/*; do
      ln -s "$f" $out/
    done
    ln -s ${zeal} $out/nixpkgs.docset.tgz
  '';
}
