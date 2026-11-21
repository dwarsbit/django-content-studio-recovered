import * as R from "ramda";

import { cn } from "@/lib/utils";
import type { Model } from "@/types";

import { Conditional } from "./conditional";
import { fieldNames } from "./conditional-fields";
import { TranslationsCard } from "./content-language";
import { EditPlacementContext } from "./edit-placement";
import { FormSet, HIDE_EMPTY_FORM_SET } from "./form-set";

export function Aside({
  model,
  hiddenFields,
}: {
  model: Model;
  hiddenFields: string[];
}) {
  const {
    admin: {
      edit: { sidebar },
    },
  } = model;
  const hasSidebar =
    (!R.isEmpty(sidebar) && !R.isNil(sidebar)) || !!model.admin.translations;

  return (
    hasSidebar && (
      <EditPlacementContext.Provider value="sidebar">
        <aside className="space-y-4">
          <TranslationsCard />
          {sidebar.map((formSet, idx) => (
            <Conditional
              key={idx}
              when={formSet.when}
              fields={fieldNames(formSet.fields)}
            >
              <section
                className={cn(
                  "rounded-lg border bg-card shadow-xs w-full",
                  HIDE_EMPTY_FORM_SET,
                )}
              >
                <FormSet
                  model={model}
                  formSet={formSet}
                  hiddenFields={hiddenFields}
                />
              </section>
            </Conditional>
          ))}
        </aside>
      </EditPlacementContext.Provider>
    )
  );
}
