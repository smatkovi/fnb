import argparse
import math
import requests
import sys

# GBFS base for Vienna (WienMobil Rad)
GBFS_VIENNA = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_wr/en/"
CITYBIKES_API = "https://api.citybik.es/v2/networks"

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def compass_direction(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    y = math.sin(dLon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
    bearing = math.degrees(math.atan2(y, x))
    compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    idx = round(((bearing + 360) % 360) / 45) % 8
    return compass[idx]

def fetch_gbfs_vienna():
    def get(endpoint, label):
        url = GBFS_VIENNA + endpoint
        print(f"Fetching {label} from {url}")
        r = requests.get(url)
        r.raise_for_status()
        return r.json()

    free_bikes = get("free_bike_status.json", "free-floating bikes")["data"]["bikes"]
    stations_info = get("station_information.json", "station info")["data"]["stations"]
    stations_status = get("station_status.json", "station status")["data"]["stations"]

    stations = {}
    for s in stations_info:
        stations[s["station_id"]] = {
            "name": s.get("name", "Unnamed"),
            "lat": s["lat"],
            "lon": s["lon"],
            "bikes": 0
        }
    for s in stations_status:
        sid = s["station_id"]
        if sid in stations:
            stations[sid]["bikes"] = s.get("num_bikes_available", 0)

    return free_bikes, list(stations.values()), "Vienna (WienMobil Rad – GBFS)"

def fetch_citybikes_data(city_name):
    print(f"Searching for '{city_name}' in Citybik.es...")
    r = requests.get(CITYBIKES_API)
    r.raise_for_status()
    matches = [
        n for n in r.json()["networks"]
        if "nextbike" in n["id"] and city_name.lower() in n["location"]["city"].lower()
    ]

    if len(matches) == 1:
        network = matches[0]
        print(f"✅ Found match: {network['location']['city']} ({network['id']})")
        url = f"https://api.citybik.es{network['href']}"
        stations = requests.get(url).json()["network"]["stations"]
        return stations, network["location"]["city"]
    elif len(matches) == 0:
        print(f"❌ No matches found for '{city_name}'. Try one of these:")
    else:
        print(f"⚠️  Multiple matches for '{city_name}':")
    all_cities = sorted([n["location"]["city"] for n in r.json()["networks"] if "nextbike" in n["id"]])
    for c in all_cities:
        print("-", c)
    sys.exit(1)

def group_and_sort_spots(lat, lon, bikes, stations, top_n=3):
    seen = set()
    spots = []

    for bike in bikes:
        lat_b, lon_b = round(bike["lat"], 5), round(bike["lon"], 5)
        key = (lat_b, lon_b)
        if key in seen: continue
        seen.add(key)
        dist = haversine_distance(lat, lon, lat_b, lon_b)
        dirn = compass_direction(lat, lon, lat_b, lon_b)
        spots.append({
            "name": f"Free-floating Bike #{bike.get('bike_id', 'unknown')}",
            "lat": lat_b,
            "lon": lon_b,
            "bikes": 1,
            "distance_km": round(dist, 3),
            "direction": dirn
        })

    for s in stations:
        if s.get("free_bikes", s.get("bikes", 0)) == 0:
            continue
        lat_s, lon_s = round(s["latitude"] if "latitude" in s else s["lat"], 5), round(s["longitude"] if "longitude" in s else s["lon"], 5)
        key = (lat_s, lon_s)
        if key in seen: continue
        seen.add(key)
        dist = haversine_distance(lat, lon, lat_s, lon_s)
        dirn = compass_direction(lat, lon, lat_s, lon_s)
        spots.append({
            "name": s.get("name", "Unnamed"),
            "lat": lat_s,
            "lon": lon_s,
            "bikes": s.get("free_bikes", s.get("bikes", 0)),
            "distance_km": round(dist, 3),
            "direction": dirn
        })

    spots.sort(key=lambda x: x["distance_km"])
    return spots[:top_n]

def main():
    parser = argparse.ArgumentParser(description="Find nearest Nextbike or GBFS bikes to coordinates.")
    parser.add_argument("lat", type=float, help="Your latitude")
    parser.add_argument("lon", type=float, help="Your longitude")
    parser.add_argument("city", nargs="?", help="Optional city name (use Vienna GBFS by default)")
    args = parser.parse_args()

    if args.city is None:
        print("📍 Defaulting to WienMobil Rad (Vienna, GBFS)...")
        bikes, stations, city = fetch_gbfs_vienna()
    else:
        stations, city = fetch_citybikes_data(args.city)
        bikes = []

    nearest = group_and_sort_spots(args.lat, args.lon, bikes, stations)

    if not nearest:
        print("No bikes found nearby.")
        return

    print(f"\n🚲 Nearest {len(nearest)} bike spots to ({args.lat}, {args.lon}) in {city}:\n")
    for spot in nearest:
        print(f"- {spot['name']}")
        print(f"  Location: ({spot['lat']}, {spot['lon']})")
        print(f"  Distance: {spot['distance_km']} km")
        print(f"  Bikes available: {spot['bikes']}")
        print(f"  Direction: {spot['direction']}")
        print(f"  Map: https://www.google.com/maps/search/?api=1&query={spot['lat']},{spot['lon']}\n")

if __name__ == "__main__":
    main()

