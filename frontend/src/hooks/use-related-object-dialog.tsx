import { useQueryClient } from "@tanstack/react-query";
import * as R from "ramda";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { RelatedObjectDialog } from "@/components/widgets/related-object-dialog";
import { useDiscover } from "@/hooks/use-discover";
import { useHttp } from "@/hooks/use-http";
import type { Model, Resource } from "@/types";

/**
 * Creating and editing the related objects of a relation picker in a
 * dialog with the related studio's own form. Creating needs the related
 * model to be registered with a studio and the user's add permission;
 * editing needs view permission (the form is read-only without change
 * permission). allow_create=False on the widget turns both off.
 *
 * Saved objects come back as the picker's options, looked up through the
 * picker's relations endpoint: a created object outside what the picker
 * offers (its get_related_<field> hook, tenant scoping) is not chosen,
 * and a warning says so.
 */
export function useRelatedObjectDialog({
  model,
  name,
  options,
  getRelationsBody,
  onCreated,
  onEdited,
}: {
  model: Model;
  name: string;
  options?: Record<string, unknown>;
  // What the picker sends the relations endpoint besides the search.
  getRelationsBody(): Record<string, unknown>;
  onCreated(option: Resource): void;
  onEdited(option: Resource): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const queryClient = useQueryClient();
  const { data: discover } = useDiscover();
  const label = model.fields[name]?.related_model;
  const related = discover?.models.find(R.whereEq({ label }));
  const enabled = !!related?.admin && options?.allow_create !== false;
  const permissions = related?.admin?.permissions;
  const canCreate = enabled && !!permissions?.add_permission;
  const canEdit = enabled && !!permissions?.view_permission;
  const [open, setOpen] = useState(false);
  // Kept while the dialog closes, so its content does not change during
  // the closing animation.
  const [target, setTarget] = useState<{
    id?: string;
    prefill?: Record<string, unknown>;
  }>({});

  const resolveOption = async (id: Resource["id"]) => {
    const { data } = await http.post<Resource[]>(
      `/content/${model.label}/relations/${name}`,
      { ...getRelationsBody(), search: "", pk: id },
    );

    return data[0] ?? null;
  };

  const openCreate = (search: string) => {
    const field = related?.admin.list.search_field;
    const text = search.trim();

    setTarget({ prefill: field && text ? { [field]: text } : undefined });
    setOpen(true);
  };

  const openEdit = (option: Resource) => {
    setTarget({ id: String(option.id) });
    setOpen(true);
  };

  const onSaved = async (saved: Resource) => {
    // The picker's options show the new or renamed object.
    await queryClient.invalidateQueries({ queryKey: ["related-model"] });

    const option = await resolveOption(saved.id);

    if (target.id) {
      onEdited(option ?? { id: saved.id, __str__: saved.__str__ });
    } else if (option) {
      onCreated(option);
    } else {
      toast.warning(
        t("widgets.relation_widget.created_not_offered", {
          item: saved.__str__,
        }),
      );
    }
  };

  const dialog =
    related && (canCreate || canEdit) ? (
      <RelatedObjectDialog
        model={related}
        id={target.id}
        prefill={target.prefill}
        readOnly={!!target.id && !permissions?.change_permission}
        open={open}
        onOpenChange={setOpen}
        onSaved={onSaved}
      />
    ) : null;

  return {
    related: related ?? null,
    canCreate,
    canEdit,
    openCreate,
    openEdit,
    dialog,
  };
}
