from bs4 import BeautifulSoup
from datetime import datetime, timezone
from collections import OrderedDict
import requests, time, json, csv, os, random

def new_payload(block, flat_type, contract, bto_date):
    return {
        "Flat": flat_type,
        "Block": block,
        "Contract": contract,
        "Town": "Toa Payoh",
        "Flat_Type": "BTO",
        "ethnic": "Y",
        "ViewOption": "A",
        "projName": "A",
        "DesType": "A",
        "EthnicA": "Y",
        "EthnicM": "",
        "EthnicC": "",
        "EthnicO": "",
        "numSPR": "",
        "dteBallot": bto_date,
        "Neighbourhood": "N9",
        "BonusFlats1": "N",
        "searchDetails": "",
        "isTownChange": "No",
        "brochure": "false"
    }

class Unit:
    def __init__(self, unit_no, booked, cost="", size=""):
        self.unit_no = unit_no
        self.booked = booked
        self.cost = cost
        self.size = size
        self.floor, self.stack = unit_no[1:].split('-')

    def update(self, block, flat_type):
        self.block = block
        self.flat_type = flat_type

    def sort_key(self):
        return [self.block, self.flat_type, self.stack, self.floor]

    def row(self):
        status = 'booked' if self.booked else 'available'
        return [self.block, self.flat_type, self.unit_no, self.floor, self.stack, status, self.size, self.cost]

    @staticmethod
    def row_header():
        return ['block', 'flat_type', 'unit_no', 'floor', 'stack', 'status', 'size', 'cost']

def unit_from_soup(soup):
  # Unbooked
  if soup.find('a'):
      u = soup.find('font')
      unit_no = u.get('id')
      cost, size = u.get('title').replace('\xa0',' ').replace('<br/>', '\n').split('____________________')
      return Unit(unit_no, False, cost.strip(), size.strip())
  else:
      unit_no = soup.find('font').text.strip()
      return Unit(unit_no, True)

def parse(html):
    soup = BeautifulSoup(html, 'html.parser')

    block_details = soup.find(id='blockDetails')
    unit_details = block_details.find_all(class_='row')[4].find_all('td')

    return [unit_from_soup(unit) for unit in unit_details]

def fetch(s, url, payload):
    return s.get(url, params=payload)

def fetch_and_parse(s, url, payload):
    r = fetch(s, url, payload)
    units = parse(r.text)
    return units

def write_json(filename, all_units):
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    unit_json = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "units": all_units
    }

    with open(filename, 'w') as out:
        out.write(json.dumps(unit_json, default=lambda obj: OrderedDict(sorted(obj.__dict__.items()))))

def write_csv(filename, all_units):
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    rows = [unit.row() for unit in all_units]
    with open(filename, 'w', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(Unit.row_header())
        writer.writerows(rows)

def flat_stats(flat_type, units):
    available = len(list(filter(lambda unit: unit.flat_type == flat_type, units)))
    booked = len(list(filter(lambda unit: unit.flat_type == flat_type and unit.booked, units)))
    return [booked, available]

def write_stats(filename, all_units, blocks_and_flat_types, expected_count):
    flat_type_count = OrderedDict()

    flat_types = sorted(expected_count.keys())

    with open(filename, 'w') as out:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        out.write("Time: {}\n".format(timestamp))

        out.write("Health check\n")
        for flat_type in flat_types:
            flat_type_count[flat_type] = len(list(filter(lambda unit: unit.flat_type == flat_type, all_units)))

        if tuple(flat_type_count.items()) == tuple(expected_count.items()):
            out.write("###OK###\n")
        else:
            out.write("\n\tTotal retrieved flats did not match expected count.\n")
            out.write("\tRetrieved: {}\n".format(tuple(flat_type_count.items())))
            out.write("\tExpected: {}\n".format(tuple(expected_count.items())))
            return

        out.write("\nCumulative Selected Stats\n")
        for flat_type in flat_types:
            booked, available = flat_stats(flat_type, all_units)
            out.write("\t{}: {}/{} ({:.2f}%) selected\n".format(flat_type, booked, available, (booked / available)*100))

        out.write("\nPer Block Selected Stats\n")
        for block, flat_types in blocks_and_flat_types.items():
            out.write("\t{}\n".format(block))
            units = list(filter(lambda unit: unit.block == block, all_units))

            for flat_type in flat_types:
                booked, available = flat_stats(flat_type, units)
                out.write("\t{}: {}/{} ({:.2f}%) selected\n".format(flat_type, booked, available, (booked / available)*100))

            out.write("\n")

def grab_data(url, blocks_and_flat_types, contracts, expected_count, filename, bto_date):
    s = requests.Session()
    # Need to make an initial request to grab the cookies
    s.get("http://services2.hdb.gov.sg/webapp/BP13AWFlatAvail/BP13EBSFlatSearch?Town=Toa%20Payoh&Flat_Type=BTO&DesType=A&ethnic=Y&Flat=4-Room&ViewOption=A&dteBallot={}&projName=A&brochure=false".format(bto_date))

    all_units = []
    debug = ""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    print("[{}] Start".format(datetime.now()))
    for block, flat_types in blocks_and_flat_types.items():
        contract = contracts[block]

        for flat_type in flat_types:
            payload = new_payload(block, flat_type, contract, bto_date)

            units = fetch_and_parse(s, url, payload)
            print("[{}] {} {}: Found {} units".format(datetime.now(), block, flat_type, len(units)))

            for i, unit in enumerate(units):
                unit.update(block, flat_type)
                units[i] = unit

            all_units.extend(units)
            time.sleep(random.uniform(0, 3))

    all_units = sorted(all_units, key=lambda unit: unit.sort_key())

    write_json("data/{}.json".format(filename), all_units)
    write_csv("data/{}.csv".format(filename), all_units)
    write_stats("data/{}.log".format(filename), all_units, blocks_and_flat_types, expected_count)
    print("[{}] End".format(datetime.now()))
    print("======================================\n")

if __name__ == "__main__":
    url = "http://services2.hdb.gov.sg/webapp/BP13AWFlatAvail/BP13EBSFlatSearch"

    # Nov 2015 selection has ended
    #blocks_and_flat_types = {
    #    "101A": ["2-Room Flexi (Short Lease/99-Year Lease)", "3-Room", "4-Room"],
    #    "102A": ["2-Room Flexi (Short Lease/99-Year Lease)", "4-Room"],
    #    "102B": ["3-Room", "4-Room"],
    #    "103A": ["3-Room", "4-Room"],
    #    "103B": ["3-Room", "4-Room"],
    #    "104A": ["2-Room Flexi (Short Lease/99-Year Lease)", "3-Room", "4-Room"],
    #    "105A": ["4-Room", "5-Room"],
    #    "105B": ["4-Room", "5-Room"],
    #    "106A": ["4-Room", "5-Room"],
    #    "106B": ["4-Room", "5-Room"],
    #    "115A": ["3-Room", "4-Room"],
    #    "115C": ["3-Room", "4-Room"],
    #    "118A": ["3-Room", "4-Room"]
    #}

    #contracts = {
    #    "101A": "C1",
    #    "102A": "C1",
    #    "102B": "C1",
    #    "103A": "C1",
    #    "103B": "C1",
    #    "104A": "C1",
    #    "105A": "C4",
    #    "105B": "C4",
    #    "106A": "C4",
    #    "106B": "C4",
    #    "115A": "C3",
    #    "115C": "C3",
    #    "118A": "C3"
    #}

    #expected_count = {
    #    "2-Room Flexi (Short Lease/99-Year Lease)": 192,
    #    "3-Room": 567,
    #    "4-Room": 1229,
    #    "5-Room": 151
    #}

    #blocks_and_flat_types = OrderedDict(sorted(blocks_and_flat_types.items()))
    #expected_count = OrderedDict(sorted(expected_count.items()))
    #grab_data(url, blocks_and_flat_types, contracts, expected_count, 'bidadari', '201511')

    blocks_and_flat_types = {
        "107A": ["3-Room", "4-Room", "5-Room"],
        "107B": ["4-Room", "5-Room"],
        "108A": ["3-Room", "4-Room"],
        "108B": ["4-Room", "5-Room"],
        "109A": ["4-Room", "5-Room"],
        "109B": ["4-Room", "5-Room"],
        "110A": ["4-Room", "5-Room"],
        "110B": ["4-Room", "5-Room"],
        "111A": ["2-Room Flexi (Short Lease/99-Year Lease)","4-Room"],
        "111B": ["2-Room Flexi (Short Lease/99-Year Lease)","4-Room"],
        "112A": ["2-Room Flexi (Short Lease/99-Year Lease)","4-Room"],
        "112B": ["3-Room", "4-Room"],
        "113A": ["3-Room", "4-Room"],
        "113B": ["3-Room", "4-Room"],
        "114A": ["2-Room Flexi (Short Lease/99-Year Lease)","3-Room", "4-Room"],
        "114B": ["2-Room Flexi (Short Lease/99-Year Lease)","3-Room", "4-Room"],
    }

    contracts = {
        "107A": "C7",
        "107B": "C7",
        "108A": "C7",
        "108B": "C7",
        "109A": "C7",
        "109B": "C7",
        "110A": "C7",
        "110B": "C7",
        "111A": "C6",
        "111B": "C6",
        "112A": "C6",
        "112B": "C6",
        "113A": "C6",
        "113B": "C6",
        "114A": "C6",
        "114B": "C6",
    }

    expected_count = {
        "2-Room Flexi (Short Lease/99-Year Lease)": 218,
        "3-Room": 340,
        "4-Room": 800,
        "5-Room": 236
    }

    blocks_and_flat_types = OrderedDict(sorted(blocks_and_flat_types.items()))
    expected_count = OrderedDict(sorted(expected_count.items()))
    grab_data(url, blocks_and_flat_types, contracts, expected_count, 'bidadari_2', '201602')
