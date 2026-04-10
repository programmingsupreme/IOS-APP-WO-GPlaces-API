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

# Overpass API endpoint (OpenStreetMap)
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

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
    regular_price: Optional[float] = None
    regular_price_formatted: Optional[str] = None
    midgrade_price: Optional[float] = None
    midgrade_price_formatted: Optional[str] = None
    premium_price: Optional[float] = None
    premium_price_formatted: Optional[str] = None
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


def extract_osm_fuel_prices(tags: dict) -> dict:
    """
    Attempt to extract fuel prices from OSM tags.
    NOTE: Real-time prices are almost never present in OSM data.
    Some mappers use tags like 'fuel:octane_87:price' = '3.459',
    but this is extremely rare. Stations will generally show N/A.
    """
    result = {
        'regular_price': None,
        'regular_price_formatted': None,
        'midgrade_price': None,
        'midgrade_price_formatted': None,
        'premium_price': None,
        'premium_price_formatted': None,
        'diesel_price': None,
        'diesel_price_formatted': None,
        'fuel_options': []
    }

    def safe_float(val):
        try:
            return round(float(val), 2) if val else None
        except (ValueError, TypeError):
            return None

    regular = safe_float(tags.get('fuel:octane_87:price') or tags.get('fuel:e10:price'))
    midgrade = safe_float(tags.get('fuel:octane_89:price'))
    premium = safe_float(
        tags.get('fuel:octane_91:price') or tags.get('fuel:octane_93:price') or tags.get('fuel:e5:price')
    )
    diesel = safe_float(tags.get('fuel:diesel:price') or tags.get('fuel:HGV_diesel:price'))

    if regular:
        result['regular_price'] = regular
        result['regular_price_formatted'] = f"${regular:.2f}"
        result['fuel_options'].append(FuelPrice(fuel_type='REGULAR_UNLEADED', price=regular, price_formatted=f"${regular:.2f}", currency='USD'))
    if midgrade:
        result['midgrade_price'] = midgrade
        result['midgrade_price_formatted'] = f"${midgrade:.2f}"
        result['fuel_options'].append(FuelPrice(fuel_type='MIDGRADE', price=midgrade, price_formatted=f"${midgrade:.2f}", currency='USD'))
    if premium:
        result['premium_price'] = premium
        result['premium_price_formatted'] = f"${premium:.2f}"
        result['fuel_options'].append(FuelPrice(fuel_type='PREMIUM', price=premium, price_formatted=f"${premium:.2f}", currency='USD'))
    if diesel:
        result['diesel_price'] = diesel
        result['diesel_price_formatted'] = f"${diesel:.2f}"
        result['fuel_options'].append(FuelPrice(fuel_type='DIESEL', price=diesel, price_formatted=f"${diesel:.2f}", currency='USD'))

    return result


async def fetch_nearby_gas_stations(latitude: float, longitude: float, radius_meters: int = 16000) -> List[dict]:
    """Fetch nearby gas stations using Overpass API (OpenStreetMap)"""
    # Overpass QL: find fuel amenities within radius, output up to 20 results with center coords
    query = (
        f"[out:json][timeout:30];"
        f"("
        f"  node[\"amenity\"=\"fuel\"](around:{radius_meters},{latitude},{longitude});"
        f"  way[\"amenity\"=\"fuel\"](around:{radius_meters},{latitude},{longitude});"
        f"  relation[\"amenity\"=\"fuel\"](around:{radius_meters},{latitude},{longitude});"
        f");"
        f"out center 20;"
    )

    async with httpx.AsyncClient(timeout=35.0) as http_client:
        try:
            response = await http_client.post(OVERPASS_API_URL, data={"data": query})
            response.raise_for_status()
            data = response.json()
            elements = data.get('elements', [])
            logger.info(f"Overpass API response: {len(elements)} stations found")
            return elements
        except httpx.HTTPStatusError as e:
            logger.error(f"Overpass API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Overpass API error: {e.response.text}")
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
    fuel_type: str = Query("regular", description="Type of fuel: 'regular', 'midgrade', 'premium', or 'diesel'")
):
    """Get nearby gas stations sorted by price (cheapest first)"""
    
    logger.info(f"Fetching stations near ({latitude}, {longitude}) for {fuel_type}")
    
    # Fetch stations from Overpass API (OpenStreetMap)
    elements = await fetch_nearby_gas_stations(latitude, longitude)

    stations = []
    bulk_operations = []

    for element in elements:
        try:
            element_type = element.get('type', 'node')
            element_id = str(element.get('id', ''))
            tags = element.get('tags', {})

            # Build a stable place_id from OSM type + id
            place_id = f"osm_{element_type}_{element_id}"

            # Station name: prefer 'name', fall back to brand / operator
            name = (
                tags.get('name')
                or tags.get('brand')
                or tags.get('operator')
                or 'Gas Station'
            )

            # Coordinates: nodes have lat/lon directly; ways/relations expose a center
            if element_type == 'node':
                place_lat = element.get('lat', 0)
                place_lng = element.get('lon', 0)
            else:
                center = element.get('center', {})
                place_lat = center.get('lat', 0)
                place_lng = center.get('lon', 0)

            # Build a human-readable address from addr:* tags
            address_parts = []
            if tags.get('addr:housenumber'):
                address_parts.append(tags['addr:housenumber'])
            if tags.get('addr:street'):
                address_parts.append(tags['addr:street'])
            if tags.get('addr:city'):
                address_parts.append(tags['addr:city'])
            if tags.get('addr:state'):
                address_parts.append(tags['addr:state'])
            address = ', '.join(address_parts) if address_parts else None

            # Calculate distance from user
            distance = calculate_distance_miles(latitude, longitude, place_lat, place_lng)

            # OSM rarely carries real-time prices; extract whatever tags exist
            prices = extract_osm_fuel_prices(tags)

            station = GasStation(
                place_id=place_id,
                name=name,
                address=address,
                latitude=place_lat,
                longitude=place_lng,
                distance_miles=distance,
                regular_price=prices['regular_price'],
                regular_price_formatted=prices['regular_price_formatted'],
                midgrade_price=prices['midgrade_price'],
                midgrade_price_formatted=prices['midgrade_price_formatted'],
                premium_price=prices['premium_price'],
                premium_price_formatted=prices['premium_price_formatted'],
                diesel_price=prices['diesel_price'],
                diesel_price_formatted=prices['diesel_price_formatted'],
                fuel_options=prices['fuel_options']
            )
            stations.append(station)

            # Persist to MongoDB
            from pymongo import UpdateOne
            bulk_operations.append(
                UpdateOne(
                    {"place_id": place_id},
                    {"$set": station.dict()},
                    upsert=True
                )
            )

        except Exception as e:
            logger.error(f"Error processing OSM element: {e}")
            continue

    # Execute bulk write to MongoDB
    if bulk_operations:
        try:
            await db.stations.bulk_write(bulk_operations, ordered=False)
        except Exception as e:
            logger.warning(f"Bulk write warning: {e}")

    # Sort: stations with prices first (cheapest → distance), then the rest by distance
    price_key_map = {
        'regular': 'regular_price',
        'midgrade': 'midgrade_price',
        'premium': 'premium_price',
        'diesel': 'diesel_price'
    }
    price_key = price_key_map.get(fuel_type, 'regular_price')

    def sort_key(station):
        price = getattr(station, price_key)
        if price is None:
            return (1, float('inf'), station.distance_miles)
        return (0, price, station.distance_miles)

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
async def get_status_checks(
    limit: int = Query(100, description="Maximum number of results", le=1000),
    skip: int = Query(0, description="Number of results to skip", ge=0)
):
    status_checks = await db.status_checks.find().skip(skip).limit(limit).to_list(limit)
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
