# QML Components Organization

This folder contains all declarative UI components.

## Organization by Feature

Components are logically grouped. When adding new components, put them in the right group:

### Navigation
- BreadcrumbAddressBar.qml
- AddressInput.qml
- Crumb.qml

### Sidebar
- Sidebar.qml
- SidebarItem.qml
- SidebarHeader.qml

### File List
- RowDelegate.qml
- FileDelegate.qml
- SelectionModel.qml

### Common / Reusable
- GtkMenu.qml
- GtkMenuSeparator.qml
- GtkScrollBar.qml
- GtkActionMenu.qml
- GtkTabButton.qml
- GtkTabBar.qml
- RubberBand.qml

### Dialogs
- RenameField.qml

## Adding New Components

1. Choose the right category above
2. Name with pattern: `<Category><Thing>.qml` (e.g., `SidebarItem.qml`)
3. Import only what you need at the top

## Qt Limitations

Qt's QML module system requires all components in a single flat folder for `import components` to work. Do NOT create subfolders here - the imports will break.