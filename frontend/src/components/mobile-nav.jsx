import { useState } from "react";
import { List } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Brand, NavItems } from "@/components/app-sidebar";

/** Mobile-only nav. The desktop rail is hidden below lg, so this keeps a way
 *  to reach every section instead of silently dropping navigation. */
export default function MobileNav({ view, onNavigate, counts }) {
  const [open, setOpen] = useState(false);

  const go = (key) => {
    onNavigate(key);
    setOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
          <List size={18} />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64">
        <SheetHeader>
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Brand />
        </SheetHeader>
        <div className="px-3">
          <NavItems view={view} onNavigate={go} counts={counts} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
