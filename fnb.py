import json
import math
import argparse
import os
import requests

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # km
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

def find_nearest_bikes(user_lat, user_lon, filepath=None, top_n=3):
    if filepath and os.path.exists(filepath):
        print(f"Reading data from {filepath}")
        with open(filepath, "r") as f:
            data = json.load(f)
    else:
        print("Fetching live data from Nextbike API...")
        url = "https://maps.nextbike.net/maps/nextbike-official.json?include_domains=de,ue,ug,um,ur,bh&city=748"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

    places = data["countries"][0]["cities"][0]["places"]
    print(f"Loaded {len(places)} places from data")

    seen_coords = set()
    bike_spots = []

    for place in places:
        bikes = place.get("bike_list", [])
        if not bikes:
            continue
        lat = round(place["lat"], 5)
        lon = round(place["lng"], 5)
        key = (lat, lon)
        if key in seen_coords:
            continue
        seen_coords.add(key)
        dist = haversine_distance(user_lat, user_lon, lat, lon)
        direction = compass_direction(user_lat, user_lon, lat, lon)
        bike_spots.append({
            "name": place.get("name", "Unnamed"),
            "lat": lat,
            "lon": lon,
            "num_bikes": len(bikes),
            "distance_km": round(dist, 3),
            "direction": direction
        })

    bike_spots.sort(key=lambda x: x["distance_km"])
    return bike_spots[:top_n]

def main():
    parser = argparse.ArgumentParser(description="Find the 3 nearest bike spots with distance and direction.")
    parser.add_argument("lat", type=float, help="Your latitude")
    parser.add_argument("lon", type=float, help="Your longitude")
    parser.add_argument("--file", type=str, default=None, help="Path to local nextbike JSON file (optional)")
    args = parser.parse_args()

    nearest = find_nearest_bikes(args.lat, args.lon, filepath=args.file)

    if not nearest:
        print("No bike locations found nearby.")
        return

    print(f"\nNearest {len(nearest)} bike spots to ({args.lat}, {args.lon}):\n")
    for spot in nearest:
        print(f"- {spot['name']}")
        print(f"  Location: ({spot['lat']}, {spot['lon']})")
        print(f"  Distance: {spot['distance_km']} km")
        print(f"  Bikes available: {spot['num_bikes']}")
        print(f"  Direction: {spot['direction']}")
        print(f"  Map: https://www.google.com/maps/search/?api=1&query={spot['lat']},{spot['lon']}\n")

if __name__ == "__main__":
    main()

