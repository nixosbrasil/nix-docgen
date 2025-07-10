const anchor = document.location.hash.substring(1);
const redirects = {"titanium": "release-notes.html#sec-nixpkgs-release-25.05-incompatibilities-titanium-removed", "building-a-titanium-app": "release-notes.html#sec-nixpkgs-release-25.05-incompatibilities-titanium-removed", "emulating-or-simulating-the-app": "release-notes.html#sec-nixpkgs-release-25.05-incompatibilities-titanium-removed"};
if (redirects[anchor]) document.location.href = redirects[anchor];
