# Aurora Better Asset Manager (ABAM)

A modern, cross-platform desktop app for managing and editing Xbox 360 Aurora dashboard artwork, title names, and synopses over FTP.

---

## Screenshots

<details>
<summary>Click to view screenshots</summary>

![Library Overview](https://i.ibb.co/N2Rz40hd/image.png)

![Asset Editor](https://i.ibb.co/9JcNsmL/image.png)

![Console Settings](https://i.ibb.co/qM9PNp88/image.png)

</details>

---

## Features

- **Artwork & Metadata Editor**: Customize covers, backgrounds, icons, banners, screenshots, titles, and synopses.
- **Console FTP Sync**: Pull and push assets directly to your Xbox 360 console.
- **Online Cover Search**: Search and fetch covers automatically from Xbox Unity and online sources.
- **Cross-Platform Engine**: Pure-Python texture processing for Linux, macOS, and Windows.
- **Demo Mode**: Test the UI offline with fake data using `python main.py --debug`.

---

## Quick Start

### Requirements
- Python 3.8+

### Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Launch application
python main.py
```

*For UI testing without an Xbox:*
```bash
python main.py --debug
```

---

## Xbox Connection Notes

- **ftpdll.xex Plugin**: Required for updating `Content.db` metadata (prevents Aurora from locking the database file). Download from [ConsoleMods](https://consolemods.org/wiki/Xbox_360:Homebrew_Apps_List#Plugins) and add to `launch.ini`.
  - Default login: `xbox` / `xbox` / Port `7564`.
- Restart Aurora on your console after pushing assets to refresh cached artwork and metadata.

---

## Credits

- XboxUnity team for original Aurora asset research.
