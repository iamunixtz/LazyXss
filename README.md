# LazyXSS - Advanced XSS Vulnerability Checker

LazyXSS is a powerful and efficient tool designed to detect Cross-Site Scripting (XSS) vulnerabilities in web applications. It supports scanning single URLs or multiple URLs from a file, allowing for customizable encoding, timeouts, and output options.

## Video Tutorial
<div align="center">
  <a href="https://youtu.be/7d0vryZCf5k">
    <img src="https://img.youtube.com/vi/7d0vryZCf5k/0.jpg" alt="LazyXSS Video Tutorial"/>
  </a>
</div>

## Features
- Single URL and bulk URL testing
- Multi-threaded scanning for enhanced performance
- Customizable payload encoding levels
- Adjustable connection timeout settings
- Export scan results to a file for later analysis
- Lightweight and easy to use

---

## Installation
To get started with LazyXSS, follow these steps:

```sh
git clone https://github.com/Iamunixtz/lazyXss.git
cd lazyXss
pip install -r requirements.txt
```

Ensure you have Python installed before running the tool.


## Usage
```sh
usage: lazyxss.py [-h] [-u URL] [-f FILE] [-t THREADS] [-e ENCODING] [-o OUTPUT] [-T TIME_SEC]
```

### Options:
- `-h, --help`           Show the help message and exit.
- `-u URL, --url URL`    Specify a single URL to test for XSS vulnerabilities.
- `-f FILE, --file FILE` Provide a file containing a list of URLs to test.
- `-t THREADS, --threads THREADS` Set the number of threads to use (default: 5).
- `-e ENCODING, --encoding ENCODING` Define the number of times to encode payloads (default: 0).
- `-o OUTPUT, --output OUTPUT` Specify a custom file name for output results (default: result.txt).
- `-T TIME_SEC, --time-sec TIME_SEC` Set connection timeout in seconds (default: 10).

---

## Example Usage
### Scan a single URL:
```sh
python lazyxss.py -u "http://example.com/search?q=test"
```

### Scan multiple URLs from a file:
```sh
python lazyxss.py -f urls.txt
```

---

## Contribution
Contributions are welcome! Feel free to submit issues or pull requests to help improve LazyXSS.

---

## License
This tool is intended for educational and ethical testing purposes only. Use responsibly and ensure you have permission before testing any website.

**Author:** Iamunixtz | [GitHub](https://github.com/Iamunixtz)

