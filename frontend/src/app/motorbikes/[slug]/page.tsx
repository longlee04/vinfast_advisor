import { notFound } from "next/navigation";

import { ProductExperience } from "@/components/product/product-experience";
import { CustomerShell } from "@/components/shared/customer-shell";
import { getMotorbikeMenuEntry, motorbikeMenuCategories } from "@/mocks/motorbike-menu";

export function generateStaticParams(): { slug: string }[] {
  return motorbikeMenuCategories.flatMap((category) =>
    category.motorbikes.map((motorbike) => ({ slug: motorbike.id })),
  );
}

export default async function MotorbikeDetailPage({
  params,
}: Readonly<{
  params: Promise<{ slug: string }>;
}>) {
  const { slug } = await params;
  const motorbike = getMotorbikeMenuEntry(slug);
  if (!motorbike) notFound();

  return (
    <CustomerShell>
      <ProductExperience
        category="motorcycle"
        categoryLabel={motorbike.categoryLabel}
        vehicle={{ ...motorbike, imageUrl: motorbike.detailImageUrl }}
      />
    </CustomerShell>
  );
}
