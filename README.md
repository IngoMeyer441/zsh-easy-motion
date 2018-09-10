# Vim's easy-motion for zsh

## Introduction

This plugin brings Vim's [easy-motion](https://github.com/easymotion/vim-easymotion) plugin to zsh. It is heavily
inspired by [zce.zsh](https://github.com/hchbaw/zce.zsh). Unfortunately, zce.zsh only supports the seek operation of
easy-motion so I have started my own implementation that adds much more easy-motion movements. Currently, the following
motions are supported: `b`, `B`, `w`, `W`, `e`, `E`, `ge`, `gE`, `f`, `F`, `t`, `T`, `c` (camelCase).


## Requirements

This plugin needs Python 2.7 or 3.3+. You can check your installed Python version with

```bash
python --version
```

If you are running a recent Linux distribution or macOS, an appropriate Python version should already be installed.


## Installation

### Using zplug

1.  Add `zplug "IngoHeimbach/zsh-easy-motion"` to your `.zshrc`.

2.  Bind a prefix key for easy-motion in `vicmd` mode, for example the `space` key:

    ```zsh
    bindkey -M vicmd ' ' vi-easy-motion
    ```

### Manual

1.  Clone this repository and source `easy_motion.plugin.zsh` in your `.zshrc`

2.  Bind a prefix key for easy-motion in `vicmd` mode, for example the `space` key:

    ```zsh
    bindkey -M vicmd ' ' vi-easy-motion
    ```


## Usage

Press the configured prefix key (for example `space`) in vi command mode and enter a vi motion command. Possible jump
targets are highlighted by red letters. Press one of the highlighted letters to jump to the corresponding position
directly.
