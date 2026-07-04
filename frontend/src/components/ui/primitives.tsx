import {
  cloneElement,
  isValidElement,
  useId,
  useState,
  type AriaAttributes,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type Key,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";

import "./primitives.css";

type ClassValue = string | false | null | undefined;

function cx(...values: ClassValue[]) {
  return values.filter(Boolean).join(" ");
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
}

export function Button({ className, type = "button", variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cx("ui-button", `ui-button--${variant}`, className)}
      type={type}
      {...props}
    />
  );
}

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function TextInput({
  "aria-invalid": ariaInvalid,
  className,
  invalid = false,
  ...props
}: TextInputProps) {
  return (
    <input
      aria-invalid={invalid ? true : ariaInvalid}
      className={cx("ui-input", className)}
      {...props}
    />
  );
}

interface DescribedControlProps {
  "aria-describedby"?: string;
  "aria-invalid"?: AriaAttributes["aria-invalid"];
  id?: string;
}

export interface FormFieldProps {
  children: ReactElement<DescribedControlProps>;
  error?: ReactNode;
  hint?: ReactNode;
  htmlFor: string;
  label: ReactNode;
}

function mergeIds(...ids: (string | undefined)[]) {
  const merged = Array.from(
    new Set(
      ids.flatMap((id) => id?.split(" ").filter(Boolean) ?? []),
    ),
  ).join(" ");

  return merged.length > 0 ? merged : undefined;
}

export function FormField({ children, error, hint, htmlFor, label }: FormFieldProps) {
  const hintId = hint ? `${htmlFor}-hint` : undefined;
  const errorId = error ? `${htmlFor}-error` : undefined;
  const describedBy = mergeIds(hintId, errorId);
  const control = isValidElement<DescribedControlProps>(children)
    ? cloneElement(children, {
        "aria-describedby": mergeIds(children.props["aria-describedby"], describedBy),
        "aria-invalid": error ? true : children.props["aria-invalid"],
        id: htmlFor,
      })
    : children;

  return (
    <div className="ui-field">
      <label className="ui-label" htmlFor={htmlFor}>
        {label}
      </label>
      {control}
      {hint ? (
        <p className="ui-field-note" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="ui-field-error" id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface AlertProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  tone?: "danger" | "info" | "success" | "warning";
}

export function Alert({ children, className, role, title, tone = "info", ...props }: AlertProps) {
  const computedRole = role ?? (tone === "danger" ? "alert" : "status");

  return (
    <div className={cx("ui-alert", `ui-alert--${tone}`, className)} role={computedRole} {...props}>
      {title ? <p className="ui-alert-title">{title}</p> : null}
      <div className="ui-alert-content">{children}</div>
    </div>
  );
}

export interface TabItem {
  content: ReactNode;
  disabled?: boolean;
  id: string;
  label: ReactNode;
}

export interface TabsProps {
  className?: string;
  defaultItemId?: string;
  items: readonly TabItem[];
  label: string;
}

export function Tabs({ className, defaultItemId, items, label }: TabsProps) {
  const baseId = useId();
  const firstEnabledItem = items.find((item) => !item.disabled) ?? items[0];
  const [activeId, setActiveId] = useState(defaultItemId ?? firstEnabledItem?.id);
  const enabledItems = items.filter((item) => !item.disabled);
  const activeItem =
    items.find((item) => item.id === activeId && !item.disabled) ?? firstEnabledItem;

  function getTabId(item: TabItem) {
    return `${baseId}-${item.id}-tab`;
  }

  function getPanelId(item: TabItem) {
    return `${baseId}-${item.id}-panel`;
  }

  function activateItem(item: TabItem | undefined) {
    if (!item || item.disabled) {
      return;
    }

    setActiveId(item.id);
    requestAnimationFrame(() => document.getElementById(getTabId(item))?.focus());
  }

  function activateByOffset(offset: number) {
    if (!activeItem || enabledItems.length === 0) {
      return;
    }

    const activeIndex = enabledItems.findIndex((item) => item.id === activeItem.id);
    const nextIndex = (activeIndex + offset + enabledItems.length) % enabledItems.length;
    activateItem(enabledItems[nextIndex]);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      activateByOffset(1);
    }

    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      activateByOffset(-1);
    }

    if (event.key === "Home") {
      event.preventDefault();
      activateItem(enabledItems[0]);
    }

    if (event.key === "End") {
      event.preventDefault();
      activateItem(enabledItems.at(-1));
    }
  }

  if (items.length === 0 || !activeItem) {
    return null;
  }

  return (
    <div className={cx("ui-tabs", className)}>
      <div aria-label={label} className="ui-tab-list" role="tablist">
        {items.map((item) => {
          const selected = item.id === activeItem.id;

          return (
            <button
              aria-controls={getPanelId(item)}
              aria-disabled={item.disabled ? true : undefined}
              aria-selected={selected}
              className="ui-tab"
              disabled={item.disabled}
              id={getTabId(item)}
              key={item.id}
              onClick={() => activateItem(item)}
              onKeyDown={handleKeyDown}
              role="tab"
              tabIndex={selected ? 0 : -1}
              type="button"
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) => {
        const selected = item.id === activeItem.id;

        return (
          <div
            aria-labelledby={getTabId(item)}
            className="ui-tab-panel"
            hidden={!selected}
            id={getPanelId(item)}
            key={item.id}
            role="tabpanel"
          >
            {item.content}
          </div>
        );
      })}
    </div>
  );
}

export interface DataTableColumn<TRow extends object> {
  align?: "left" | "right";
  header: ReactNode;
  key: keyof TRow & string;
  render?: (row: TRow) => ReactNode;
}

export interface DataTableProps<TRow extends object> {
  caption: ReactNode;
  columns: readonly DataTableColumn<TRow>[];
  emptyMessage?: ReactNode;
  rowKey: (row: TRow) => Key;
  rows: readonly TRow[];
}

function renderCellValue<TRow extends object>(row: TRow, column: DataTableColumn<TRow>) {
  if (column.render) {
    return column.render(row);
  }

  const value = row[column.key];

  if (typeof value === "string" || typeof value === "number") {
    return value;
  }

  if (value == null) {
    return "";
  }

  return JSON.stringify(value);
}

export function DataTable<TRow extends object>({
  caption,
  columns,
  emptyMessage = "No rows to display.",
  rowKey,
  rows,
}: DataTableProps<TRow>) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th className={cx(column.align === "right" && "ui-cell--right")} key={column.key}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length > 0 ? (
            rows.map((row) => (
              <tr key={rowKey(row)}>
                {columns.map((column) => (
                  <td className={cx(column.align === "right" && "ui-cell--right")} key={column.key}>
                    {renderCellValue(row, column)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-empty-cell" colSpan={columns.length}>
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
