from geopy.geocoders import Nominatim
import re
import sys
import ssl
import ssl
import certifi
import os

# Force using custom CA cert
os.environ['SSL_CERT_FILE'] = certifi.where()




def is_coordinates(query):
    """
    Check if input looks like GPS coordinates.
    Accepts formats like "48.0, 16.0" or "48, 16"
    """
    coord_pattern = re.compile(r'^-?\d{1,3}(?:[.,]\d+)?,\s*-?\d{1,3}(?:[.,]\d+)?$')
    return bool(coord_pattern.match(query.strip()))

def address_to_coordinates(address, geolocator):
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
    except Exception as e:
        print(f"Error: {e}")
    return None

def coordinates_to_address(coords, geolocator):
    try:
        # SPLIT FIRST
        lat_str, lon_str = coords.split(',')

        # CLEAN EACH ONE
        lat = float(lat_str.strip().replace(',', '.'))
        lon = float(lon_str.strip().replace(',', '.'))

        location = geolocator.reverse((lat, lon), timeout=10)
        if location:
            return location.address
    except Exception as e:
        print(f"Error: {e}")
    return None

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 gpstoadd.py '<address OR lat,lon>'")
        sys.exit(1)

    query = sys.argv[1].strip()

    # Use a proper user-agent (email or something unique)
    geolocator = Nominatim(user_agent="sebastianmatkovich@gmail.com")

    if is_coordinates(query):
        address = coordinates_to_address(query, geolocator)
        if address:
            print(f"Address: {address}")
        else:
            print("Could not find an address for these coordinates.")
    else:
        coords = address_to_coordinates(query, geolocator)
        if coords:
            print(f"Coordinates: {coords[0]}, {coords[1]}")
        else:
            print("Could not find coordinates for this address.")

if __name__ == "__main__":
    main()

