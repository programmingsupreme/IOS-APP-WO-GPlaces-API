from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import httpx
from geopy.distance import geodesic
import math

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Google Places API Key
GOOGLE_PLACES_API_KEY = "AIzaSyDkyWP12O7MPEu-s3W4ayfWpVZ1y4_WDAo"

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Models
class FuelPrice(BaseModel):
    fuel_type: str
    price: Optional[float] = None
    price_formatted: Optional[str] = None
    currency: Optional[str] = None
    last_updated: Optional[str] = None

class GasStation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    place_id: str
    name: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    distance_miles: float
    gas_price: Optional[float] = None
    gas_price_formatted: Optional[str] = None
    diesel_price: Optional[float] = None
    diesel_price_formatted: Optional[str] = None
    fuel_options: List[FuelPrice] = []
    last_fetched: datetime = Field(default_factory=datetime.utcnow)

class GasStationResponse(BaseModel):
    stations: List[GasStation]
    fuel_type: str
    user_location: dict
    total_found: int

class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str


def calculate_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in miles"""
    try:
        distance_km = geodesic((lat1, lon1), (lat2, lon2)).kilometers
        return round(distance_km * 0.621371, 2)  # Convert to miles
    except Exception:
        return 0.0


def parse_fuel_price(price_data: dict) -> tuple:
    """Parse fuel price from Google Places API response"""
    try:
        # The price object has 'units' and 'nanos' fields
        if 'price' in price_data:
            price_obj = price_data['price']
            units = int(price_obj.get('units', 0))
            nanos = int(price_obj.get('nanos', 0))
            # Convert nanos to decimal (nanos are 10^-9)
            price = units + (nanos / 1_000_000_000)
            currency = price_obj.get('currencyCode', 'USD')
            return round(price, 2), currency
    except Exception as e:
        logger.error(f"Error parsing fuel price: {e}")
    return None, None


def extract_fuel_prices(fuel_options: dict) -> dict:
    """Extract gas and diesel prices from fuel options"""
    result = {
        'gas_price': None,
        'gas_price_formatted': None,
        'diesel_price': None,
        'diesel_price_formatted': None,
        'fuel_options': []
    }
    
    if not fuel_options or 'fuelPrices' not in fuel_options:
        return result
    
    for fuel_price in fuel_options.get('fuelPrices', []):
        fuel_type = fuel_price.get('type', '')
        price, currency = parse_fuel_price(fuel_price)
        
        fuel_entry = FuelPrice(
            fuel_type=fuel_type,
            price=price,
            price_formatted=f"${price:.2f}" if price else None,
            currency=currency,
            last_updated=fuel_price.get('updateTime')
        )
        result['fuel_options'].append(fuel_entry)
        
        # Map to gas (regular unleaded) or diesel
        if fuel_type in ['REGULAR_UNLEADED', 'MIDGRADE', 'PREMIUM']:
            if result['gas_price'] is None or fuel_type == 'REGULAR_UNLEADED':
                result['gas_price'] = price
                result['gas_price_formatted'] = f"${price:.2f}" if price else None
        elif fuel_type == 'DIESEL':
            result['diesel_price'] = price
            result['diesel_price_formatted'] = f"${price:.2f}" if price else None
    
    return result


async def fetch_nearby_gas_stations(latitude: float, longitude: float, radius_meters: int = 16000) -> List[dict]:
    """Fetch nearby gas stations using Google Places API (New)"""
    url = "https://places.googleapis.com/v1/places:searchNearby"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.fuelOptions"
    }
    
    payload = {
        "includedTypes": ["gas_station"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": radius_meters
            }
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Google Places API response: {len(data.get('places', []))} stations found")
            return data.get('places', [])
        except httpx.HTTPStatusError as e:
            logger.error(f"Google Places API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Google Places API error: {e.response.text}")
        except Exception as e:
            logger.error(f"Error fetching gas stations: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching gas stations: {str(e)}")


@api_router.get("/")
async def root():
    return {"message": "Fuel Finder API", "version": "1.0.0"}


@api_router.get("/stations", response_model=GasStationResponse)
async def get_nearby_stations(
    latitude: float = Query(..., description="User's latitude"),
    longitude: float = Query(..., description="User's longitude"),
    fuel_type: str = Query("gas", description="Type of fuel: 'gas' or 'diesel'")
):
    """Get nearby gas stations sorted by price (cheapest first)"""
    
    logger.info(f"Fetching stations near ({latitude}, {longitude}) for {fuel_type}")
    
    # Fetch stations from Google Places API
    places = await fetch_nearby_gas_stations(latitude, longitude)
    
    stations = []
    for place in places:
        try:
            place_id = place.get('id', '')
            name = place.get('displayName', {}).get('text', 'Unknown Station')
            address = place.get('formattedAddress', '')
            location = place.get('location', {})
            place_lat = location.get('latitude', 0)
            place_lng = location.get('longitude', 0)
            
            # Calculate distance
            distance = calculate_distance_miles(latitude, longitude, place_lat, place_lng)
            
            # Extract fuel prices
            fuel_options = place.get('fuelOptions', {})
            prices = extract_fuel_prices(fuel_options)
            
            station = GasStation(
                place_id=place_id,
                name=name,
                address=address,
                latitude=place_lat,
                longitude=place_lng,
                distance_miles=distance,
                gas_price=prices['gas_price'],
                gas_price_formatted=prices['gas_price_formatted'],
                diesel_price=prices['diesel_price'],
                diesel_price_formatted=prices['diesel_price_formatted'],
                fuel_options=prices['fuel_options']
            )
            stations.append(station)
            
            # Cache in MongoDB
            await db.stations.update_one(
                {"place_id": place_id},
                {"$set": station.dict()},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"Error processing station: {e}")
            continue
    
    # Sort by price (cheapest first)
    # Stations without prices go to the end
    price_key = 'gas_price' if fuel_type == 'gas' else 'diesel_price'
    
    def sort_key(station):
        price = getattr(station, price_key)
        if price is None:
            return (1, float('inf'), station.distance_miles)  # No price - sort last
        return (0, price, station.distance_miles)  # Has price - sort by price, then distance
    
    stations.sort(key=sort_key)
    
    # Return top 10
    top_stations = stations[:10]
    
    return GasStationResponse(
        stations=top_stations,
        fuel_type=fuel_type,
        user_location={"latitude": latitude, "longitude": longitude},
        total_found=len(stations)
    )


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
