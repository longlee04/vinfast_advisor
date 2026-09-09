import { LocationFinder } from "@/components/locations/location-finder";
import { CustomerShell } from "@/components/shared/customer-shell";

export default function LocationsPage() {
  return (
    <CustomerShell>
      <LocationFinder />
    </CustomerShell>
  );
}
