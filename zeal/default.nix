{ pkgs
, nixpkgs-flake
, nixpkgs-path
, rev
}:
let
  inherit (nixpkgs-flake.defaultNix.htmlDocs) nixpkgsManual nixosManual;
  infoPlist = builtins.toFile "Info.plist" ''
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleIdentifier</key>
	<string>nixpkgs-${rev}</string>
	<key>CFBundleName</key>
	<string>Nixpkgs (branch ${rev})</string>
	<key>DocSetPlatformFamily</key>
	<string>nixpkgs</string>
	<key>isDashDocset</key>
	<true/>
    <key>dashIndexFilePath</key>
    <string>index.html</string>
</dict>
</plist>
  '';
  pythonInterpreter = (pkgs.python3.withPackages (p: with p; [ beautifulsoup4 ])).interpreter;
 packageContent = pkgs.stdenv.mkDerivation {
    name = "nixpkgs-${rev}.docset";
    dontUnpack = true;
    nativeBuildInputs = with pkgs; [ nix-doc nixpkgs-path ];
    installPhase = ''
      mkdir -p $out/Contents/Resources/Documents -p
      ln -s ${infoPlist} $out/Contents/Info.plist
      ${pythonInterpreter} ${./generate_index.py} -b ${rev} --nixpkgs ${nixpkgs-path} --output "$out/Contents/Resources/Documents/index.html" --index $out/Contents/Resources/docSet.dsidx
    '';
  };
  tarball = pkgs.stdenv.mkDerivation {
    name = "nixpkgs-${rev}.docset.tgz";
    dontUnpack = true;
    installPhase = ''
      tar -cvzf $out ${packageContent}
    '';
  };
in tarball
