const anchor = document.location.hash.substring(1);
const redirects = {"sec-nixpkgs-release-25.05-incompatibilities-nexusmods-app-upgraded": "release-notes.html#sec-nixpkgs-release-25.05-incompatibilities"};
if (redirects[anchor]) document.location.href = redirects[anchor];
