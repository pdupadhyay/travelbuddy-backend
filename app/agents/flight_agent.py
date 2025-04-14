import httpx
from app.config import settings
from datetime import datetime, timedelta
import json
from app.agents.airport_codes import get_airport_code

AMADEUS_API_URL = "https://test.api.amadeus.com/v2"
TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"

def simplify_flight_data(flight_data: dict) -> dict:
    """Simplify the flight data to include only essential information, preserving all connections."""
    simplified_flights = []
    
    for flight in flight_data.get("data", []):
        # Get all segments for outbound and return journeys
        outbound_segments = flight["itineraries"][0]["segments"]
        return_segments = flight["itineraries"][1]["segments"]
        
        # Convert price to USD if needed
        price = flight["price"]
        if price["currency"] != "USD":
            price["currency"] = "USD"
        
        # Process all outbound segments
        processed_outbound = []
        for segment in outbound_segments:
            processed_outbound.append({
                "departure": {
                    "airport": segment["departure"]["iataCode"],
                    "time": segment["departure"]["at"],
                    "terminal": segment["departure"].get("terminal", "")
                },
                "arrival": {
                    "airport": segment["arrival"]["iataCode"],
                    "time": segment["arrival"]["at"],
                    "terminal": segment["arrival"].get("terminal", "")
                },
                "duration": segment["duration"],
                "airline": segment.get("carrierCode", flight["validatingAirlineCodes"][0]),
                "flight_number": segment["number"]
            })
        
        # Process all return segments
        processed_return = []
        for segment in return_segments:
            processed_return.append({
                "departure": {
                    "airport": segment["departure"]["iataCode"],
                    "time": segment["departure"]["at"],
                    "terminal": segment["departure"].get("terminal", "")
                },
                "arrival": {
                    "airport": segment["arrival"]["iataCode"],
                    "time": segment["arrival"]["at"],
                    "terminal": segment["arrival"].get("terminal", "")
                },
                "duration": segment["duration"],
                "airline": segment.get("carrierCode", flight["validatingAirlineCodes"][0]),
                "flight_number": segment["number"]
            })
        
        # Create the simplified flight with all segments
        simplified_flight = {
            "price": {
                "total": price["total"],
                "currency": "USD"
            },
            "outbound": {
                "segments": processed_outbound,
                "total_duration": flight["itineraries"][0].get("duration", ""),
                "stops": len(processed_outbound) - 1
            },
            "return": {
                "segments": processed_return,
                "total_duration": flight["itineraries"][1].get("duration", ""),
                "stops": len(processed_return) - 1
            }
        }
        simplified_flights.append(simplified_flight)
    
    return {
        "flights": simplified_flights,
        "total_offers": flight_data.get("meta", {}).get("count", len(simplified_flights))
    }

async def get_flight_offers(origin: str, destination: str, departure_date: str, return_date: str) -> dict:
    # First get the access token
    token = await get_access_token()
    
    # Convert city names to airport codes
    origin_code = await get_airport_code(origin)
    destination_code = await get_airport_code(destination)
    
    # Check if dates are too far in the future
    today = datetime.now().date()
    departure = datetime.strptime(departure_date, "%Y-%m-%d").date()
    return_dt = datetime.strptime(return_date, "%Y-%m-%d").date()
    
    # Calculate months difference
    months_diff = (departure.year - today.year) * 12 + departure.month - today.month
    
    if months_diff > 11:
        return {
            "message": "Flight search is currently available for dates within the next 11 months.",
            "suggestion": "Please check back closer to your travel date for available flights.",
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
            "origin_code": origin_code,
            "destination_code": destination_code
        }
    
    # Search for flights
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Create the request body as required by the Amadeus API
    request_body = {
        "currencyCode": "USD",
        "originDestinations": [
            {
                "id": "1",
                "originLocationCode": origin_code,
                "destinationLocationCode": destination_code,
                "departureDateTimeRange": {
                    "date": departure_date
                }
            },
            {
                "id": "2",
                "originLocationCode": destination_code,
                "destinationLocationCode": origin_code,
                "departureDateTimeRange": {
                    "date": return_date
                }
            }
        ],
        "travelers": [
            {
                "id": "1",
                "travelerType": "ADULT"
            }
        ],
        "sources": ["GDS"],
        "searchCriteria": {
            "maxFlightOffers": 5,
            "flightFilters": {
                "cabinRestrictions": [
                    {
                        "cabin": "ECONOMY",
                        "coverage": "MOST_SEGMENTS",
                        "originDestinationIds": ["1", "2"]
                    }
                ]
            }
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AMADEUS_API_URL}/shopping/flight-offers",
            headers=headers,
            json=request_body,
        )
        
        if response.status_code == 200:
            data = response.json()
            if not data.get("data"):
                return {
                    "message": "No flights found for the selected dates.",
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date,
                    "return_date": return_date,
                    "origin_code": origin_code,
                    "destination_code": destination_code
                }
            
            # Sort flights by price
            sorted_flights = sorted(data["data"], key=lambda x: float(x["price"]["total"]))
            data["data"] = sorted_flights
            
            return simplify_flight_data(data)
        else:
            return {
                "error": "Failed to fetch flight offers",
                "status_code": response.status_code,
                "details": response.text
            }

async def get_access_token() -> str:
    params = {
        "grant_type": "client_credentials",
        "client_id": settings.AMADEUS_API_KEY,
        "client_secret": settings.AMADEUS_API_SECRET
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_URL, data=params)
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            raise Exception("Failed to get access token from Amadeus API")