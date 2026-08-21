"""Import a normalized FAA FRQ.csv into the runtime channel catalog."""
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); channels=[]
    with a.input.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try: mhz=float(row.get("FREQ", "")); lat=float(row.get("LAT_DECIMAL", "0")); lon=float(row.get("LONG_DECIMAL", "0"))
            except ValueError: continue
            if not 118.0 <= mhz <= 136.975 or row.get("SERVICED_COUNTRY", "US").strip().upper() not in ("", "US"): continue
            use=row.get("FREQ_USE", "").strip(); facility=row.get("SERVICED_FACILITY", "").strip().upper()
            if not facility: continue
            channels.append({"frequency_hz":round(mhz*1_000_000),"frequency_mhz":mhz,"frequency_use":use,"category":use,"serviced_facility":facility,"serviced_facility_name":row.get("SERVICED_FAC_NAME", "").strip(),"city":row.get("SERVICED_CITY", "").strip(),"state":row.get("SERVICED_STATE", "").strip(),"latitude":lat,"longitude":lon})
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps({"schema_version":1,"source":"FAA NASR FRQ.csv","channels":channels},indent=2)+"\n",encoding="utf-8"); print(f"wrote {len(channels)} channels to {a.output}")
if __name__ == "__main__": main()
