import httpx
from app.config import settings

async def get_airport_code(city_name: str) -> str:
    """
    Convert a city name to its IATA airport code using Amadeus API.
    Returns the most relevant airport code for the given city.
    """
    # Clean the city name - take only the first part before any comma
    clean_city = city_name.split(',')[0].strip()
    
    # First get the access token
    token = await get_access_token()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    params = {
        "keyword": clean_city,
        "subType": "CITY,AIRPORT",
        "countryCode": "US",  # Add country code for US cities
        "page[limit]": 10,
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://test.api.amadeus.com/v1/reference-data/locations",
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            data = response.json()
            locations = data.get("data", [])
            
            if not locations:
                common_airports = {
                    "new york": "JFK",
                    "los angeles": "LAX",
                    "chicago": "ORD",
                    "san francisco": "SFO",
                    "miami": "MIA",
                    "dallas": "DFW",
                    "houston": "IAH",
                    "atlanta": "ATL",
                    "washington d.c.": "DCA",
                    "boston": "BOS"
                }
                
                for city_key, code in common_airports.items():
                    if city_key in clean_city.lower():
                        return code
                
                return clean_city[:3].upper()  # Last resort fallback
            
            # Try to find the most relevant airport
            for location in locations:
                # Check if it's an airport
                if location.get("subType") == "AIRPORT":
                    return location.get("iataCode", location.get("id"))
            
            # If no airport found, return the first city's code
            return locations[0].get("iataCode", locations[0].get("id"))
            
        error_detail = f"API Error: {response.status_code}"
        try:
            error_detail += f" - {response.json()}"
        except:
            error_detail += f" - {response.text}"
            
        print(f"Airport lookup error: {error_detail}")
        
        # Fallback to a simple abbreviation if API fails
        return city_name.strip().upper()[:3]

async def get_access_token() -> str:
    params = {
        "grant_type": "client_credentials",
        "client_id": settings.AMADEUS_API_KEY,
        "client_secret": settings.AMADEUS_API_SECRET
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data=params
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            raise Exception("Failed to get access token from Amadeus API") 