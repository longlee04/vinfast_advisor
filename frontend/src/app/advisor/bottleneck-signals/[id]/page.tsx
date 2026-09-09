import { BottleneckSignalPanel } from "@/components/advisor/bottleneck-signal-panel";
import { OperationalShell } from "@/components/shared/operational-shell";

export default async function BottleneckSignalPage({ params }: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;
  return <OperationalShell role="advisor"><BottleneckSignalPanel signalId={id} /></OperationalShell>;
}
