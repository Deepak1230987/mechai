import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { OperationRow } from "./OperationRow";
import type { Operation } from "@/types/machining";

interface OperationListProps {
  operations: Operation[];
  toolIds: string[];
  onUpdate: (id: string, patch: Partial<Operation>) => void;
  onDelete: (id: string) => void;
  onReorder: (fromIndex: number, toIndex: number) => void;
  onAdd: () => void;
}

export function OperationList({
  operations,
  toolIds,
  onUpdate,
  onDelete,
  onReorder,
  onAdd,
}: OperationListProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = operations.findIndex((o) => o.id === active.id);
    const newIndex = operations.findIndex((o) => o.id === over.id);
    if (oldIndex !== -1 && newIndex !== -1) {
      onReorder(oldIndex, newIndex);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">
          Operations ({operations.length})
        </h2>
        <Button variant="outline" size="sm" onClick={onAdd}>
          <Plus className="mr-1 size-4" />
          Add Operation
        </Button>
      </div>

      <ScrollArea className="max-h-125">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={operations.map((o) => o.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="flex flex-col gap-1.5 pr-3">
              {operations.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No operations yet. Click "Add Operation" to get started.
                </p>
              ) : (
                operations.map((op, idx) => (
                  <OperationRow
                    key={op.id}
                    operation={op}
                    index={idx}
                    toolIds={toolIds}
                    onUpdate={onUpdate}
                    onDelete={onDelete}
                  />
                ))
              )}
            </div>
          </SortableContext>
        </DndContext>
      </ScrollArea>
    </div>
  );
}
