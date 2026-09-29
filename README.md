# OpenTW API

OpenTW API is a service that parses data from TrackWrestling's website and returns it in a simplified, structured format. This API makes it easier for developers to access and utilize wrestling tournament data.

## Overview

The OpenTW API serves as a middleware between applications and TrackWrestling's website, providing a cleaner interface to access tournament information, match details, brackets, and more. It handles the scraping and parsing of data, allowing developers to focus on building features rather than dealing with data extraction.

## Features

- Search for tournaments
- Get detailed tournament information
- Retrieve live match assignments and status
- Access bracket information
- Monitor match status changes
- RESTful API with JSON responses

## API Endpoints

### Search Tournaments
```
GET /tournaments?query={search_term}
```
Returns a list of tournaments matching the search term.

### Tournament Information
```
GET /tournaments/{tournament_type}/{tournament_id}
```
Returns detailed information about a specific tournament.

### Match Assignments
```
GET /tournaments/{tournament_type}/{tournament_id}/matches
```
Returns current match assignments and statuses for a tournament.

### Brackets
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets
```
Returns bracket information for all weight classes in a tournament.

### Specific Bracket
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets/{weight_class_id}
```
Returns detailed bracket information for a specific weight class.

## Installation

### Prerequisites
- Python 3.8+
- pip
- asyncio support

### Setup
1. Clone the repository:
   ```
   git clone https://github.com/vehbiu/opentw-api.git
   cd opentw-api
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the server:
   ```
   python main.py
   ```
   Host and port come from `HOST` and `PORT` (defaults `localhost:8000`).

4. Check it still works against the live site:
   ```
   python smoke_test.py
   ```
   `python test_parsers.py` checks the parsing edge cases offline.

The server will start on `localhost:8000` by default.

## Development

The API is built using:
- Sanic - Async Python web server
- aiohttp - Async HTTP client for fetching data
- Custom parsers for extracting data from TrackWrestling HTML

### A warning about the parsers

This scrapes a site nobody here controls, and TrackWrestling changes it. The failures are
quiet ones: a page that returns 200 with a different shape, a row silently dropped, a field
that shifts one position. `smoke_test.py` exists because "it imports and the server starts"
says nothing at all about whether the parsing still works.

If something looks wrong, run the smoke test first - it checks the values, not just the
status codes.

### Project Structure
- `main.py` - Entry point; reads HOST/PORT and runs the server
- `server.py` - Sanic app and route definitions
- `smoke_test.py` - End-to-end checks against the live site
- `test_parsers.py` - Offline checks of the parsing edge cases
- `models/` - Data models and types
- `parsers/` - HTML parsing logic for different TrackWrestling views

## Live Demo

A live version of the API is available at: https://opentw-api.vehbi.me

## Related Projects

- [OpenTW](https://github.com/vehbiu/opentw) - Frontend interface for this API

## License

[MIT License](LICENSE)

## Contact

For issues and contributions, please visit the [GitHub repository](https://github.com/vehbiu/opentw-api).