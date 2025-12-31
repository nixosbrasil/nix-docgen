# :us: nix-docgen
Generate documentation of different nixpkgs branches and upload to GitHub Pages.

This repository builds the already provided nixpkgs documentation daily using GitHub Actions and hosts in a GitHub Pages endpoint.

If you want to track a custom branch, fork or nixpkgs tarball you can setup your own sources. The branch notation defaults to the main
nixpkgs fork but you can use any website that can emit a .tar.gz file with the repo contents.

On GitHub Actions you can setup the sources using a secret named `BRANCHES` separated by space.

# :brazil: nix-docgen
Gere documentação de diferentes ramificações do nixpkgs e mande para o GitHub Pages.

Este repositório compila a documentação já fornecida pelo nixpkgs diariamente usando o GitHub Actions e lança como um site no GitHub pages.

Se você desejar rastrear uma ramificação customizada, fork ou tarball do nixpkgs você pode configurar suas próprias fontes. A notação de 
ramificação por padrão aponta para o repositório principal do nixpkgs mas você pode usar qualquer site que permite baixar um .tar.gz
com os conteúdos do repositório.

No GitHub Actions você pode configurar as fontes usando um secret com nome `BRANCHES` separando cada elemento por um espaço.
