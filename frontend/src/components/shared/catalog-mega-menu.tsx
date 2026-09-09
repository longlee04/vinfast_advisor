"use client";

import { ChevronDown } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export type CatalogMegaMenuItem = {
  id: string;
  name: string;
  href: string;
  imageUrl: string;
};

export type CatalogMegaMenuCategory = {
  id: string;
  label: string;
  items: CatalogMegaMenuItem[];
};

function CatalogCategoryTabs({
  activeCategory,
  categories,
  idPrefix,
  onChange,
}: Readonly<{
  activeCategory: string;
  categories: CatalogMegaMenuCategory[];
  idPrefix: string;
  onChange: (category: string) => void;
}>) {
  function moveTabFocus(event: React.KeyboardEvent<HTMLButtonElement>): void {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;

    const tabs = Array.from(
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("[role='tab']") ?? [],
    );
    const currentIndex = tabs.indexOf(event.currentTarget);
    if (currentIndex < 0) return;

    event.preventDefault();
    let nextIndex = currentIndex;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    tabs[nextIndex]?.focus();
    tabs[nextIndex]?.click();
  }

  return (
    <div className="vehicle-menu-tabs" aria-label="Chọn phân khúc sản phẩm" role="tablist">
      {categories.map((category) => (
        <button
          aria-controls={`${idPrefix}-panel`}
          aria-selected={activeCategory === category.id}
          className={activeCategory === category.id ? "is-active" : ""}
          id={`${idPrefix}-tab-${category.id}`}
          key={category.id}
          onClick={() => onChange(category.id)}
          onKeyDown={moveTabFocus}
          role="tab"
          tabIndex={activeCategory === category.id ? 0 : -1}
          type="button"
        >
          {category.label}
        </button>
      ))}
    </div>
  );
}

function CatalogMenuPanel({
  activeCategory,
  categories,
  idPrefix,
  onItemClick,
}: Readonly<{
  activeCategory: string;
  categories: CatalogMegaMenuCategory[];
  idPrefix: string;
  onItemClick: () => void;
}>) {
  const category = categories.find((item) => item.id === activeCategory) ?? categories[0];
  if (!category) return null;

  return (
    <div
      aria-labelledby={`${idPrefix}-tab-${category.id}`}
      className="vehicle-mega-menu-grid"
      data-category={category.id}
      id={`${idPrefix}-panel`}
      role="tabpanel"
    >
      {category.items.map((item) => (
        <Link className="vehicle-mega-card" href={item.href} key={item.id} onClick={onItemClick}>
          <span className="vehicle-mega-visual">
            <Image alt="" fill sizes="180px" src={item.imageUrl} />
          </span>
          <strong>{item.name}</strong>
        </Link>
      ))}
    </div>
  );
}

export function CatalogMegaMenu({
  categories,
  defaultCategory,
  idPrefix,
  triggerLabel,
}: Readonly<{
  categories: CatalogMegaMenuCategory[];
  defaultCategory: string;
  idPrefix: string;
  triggerLabel: string;
}>) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeCategory, setActiveCategory] = useState(defaultCategory);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent): void {
      if (!containerRef.current?.contains(event.target as Node)) setIsOpen(false);
    }

    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key !== "Escape") return;
      setIsOpen(false);
      triggerRef.current?.focus();
    }

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return (
    <div className="vehicle-nav-item" ref={containerRef}>
      <button
        aria-controls={`${idPrefix}-menu`}
        aria-expanded={isOpen}
        className="vehicle-nav-trigger"
        onClick={() => setIsOpen((open) => !open)}
        ref={triggerRef}
        type="button"
      >
        {triggerLabel} <ChevronDown aria-hidden="true" className={isOpen ? "is-open" : ""} size={15} />
      </button>

      {isOpen ? (
        <div className="vehicle-mega-menu" id={`${idPrefix}-menu`}>
          <div className="vehicle-mega-menu-inner">
            <CatalogCategoryTabs
              activeCategory={activeCategory}
              categories={categories}
              idPrefix={idPrefix}
              onChange={setActiveCategory}
            />
            <CatalogMenuPanel
              activeCategory={activeCategory}
              categories={categories}
              idPrefix={idPrefix}
              onItemClick={() => setIsOpen(false)}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function MobileCatalogMenu({
  ariaLabel,
  categories,
  defaultCategory,
  idPrefix,
  onItemClick,
}: Readonly<{
  ariaLabel: string;
  categories: CatalogMegaMenuCategory[];
  defaultCategory: string;
  idPrefix: string;
  onItemClick: () => void;
}>) {
  const [activeCategory, setActiveCategory] = useState(defaultCategory);

  return (
    <section className="mobile-vehicle-menu" aria-label={ariaLabel}>
      <CatalogCategoryTabs
        activeCategory={activeCategory}
        categories={categories}
        idPrefix={idPrefix}
        onChange={setActiveCategory}
      />
      <CatalogMenuPanel
        activeCategory={activeCategory}
        categories={categories}
        idPrefix={idPrefix}
        onItemClick={onItemClick}
      />
    </section>
  );
}
