# XSpace Downloader Theme System

## Overview

The XSpace Downloader now includes a comprehensive theme system that allows users to choose from multiple color schemes, each with both light and dark mode variants.

## Available Themes

### 1. Default Theme (Blue & Gray)
- **Primary**: Blue (#0d6efd)
- **Style**: Classic, professional
- **Best for**: Standard usage, business environments

### 2. Ocean Theme (Teal & Cyan)
- **Primary**: Teal (#20c997)
- **Style**: Cool, refreshing
- **Best for**: Creative work, calm environments

### 3. Sunset Theme (Orange & Pink)
- **Primary**: Orange (#f97316)
- **Style**: Warm, energetic
- **Best for**: Creative projects, vibrant workflows

### 4. Forest Theme (Green & Nature)
- **Primary**: Green (#059669)
- **Style**: Natural, calming
- **Best for**: Long work sessions, nature enthusiasts

## How to Use

1. **Theme Selector**: Click the palette icon (🎨) in the top navigation bar
2. **Choose Color Scheme**: Select from Default, Ocean, Sunset, or Forest themes
3. **Toggle Dark Mode**: Use the sun/moon toggle within the theme selector
4. **Automatic Persistence**: Your preferences are saved in browser localStorage

## Features

- **Responsive Design**: All themes work on desktop and mobile
- **System Preference Detection**: Automatically detects your system's light/dark preference
- **Smooth Transitions**: Color changes are animated for a polished experience
- **Consistent Branding**: All UI elements (buttons, cards, forms) adapt to the selected theme

## Technical Implementation

- **CSS Custom Properties**: Uses CSS variables for dynamic theming
- **Bootstrap Integration**: Leverages Bootstrap 5's theme system
- **LocalStorage Persistence**: Saves `colorTheme` and `mode` preferences
- **JavaScript Theme Engine**: Handles theme switching and initialization

## File Structure

```
static/
├── themes.css          # Theme definitions and styling
└── favicon.svg         # App icon

templates/
└── base.html           # Theme selector UI and JavaScript
```

## Theme Development

To add a new theme:

1. **Define CSS Variables** in `static/themes.css`:
   ```css
   [data-theme="mytheme"] {
       --bs-primary: #color;
       --bs-primary-rgb: r, g, b;
       --bs-secondary: #color;
       --bs-secondary-rgb: r, g, b;
       /* ... other variables ... */
   }
   ```

2. **Add Dark Mode Variant**:
   ```css
   [data-theme="mytheme"][data-bs-theme="dark"] {
       --bs-body-bg: #dark-bg;
       --bs-body-color: #light-text;
       /* ... dark mode overrides ... */
   }
   ```

3. **Update Theme Selector** in `base.html`:
   ```html
   <div class="theme-option" data-theme="mytheme">
       <div class="theme-color-preview"></div>
       <div>
           <div class="fw-medium">My Theme</div>
           <small class="text-muted">Description</small>
       </div>
   </div>
   ```

4. **Add Color Preview** in `themes.css`:
   ```css
   .theme-option[data-theme="mytheme"] .theme-color-preview::before {
       background: #primary-color;
   }
   .theme-option[data-theme="mytheme"] .theme-color-preview::after {
       background: #secondary-color;
   }
   ```

## Browser Support

- **Modern Browsers**: Chrome 88+, Firefox 85+, Safari 14+, Edge 88+
- **CSS Variables**: Full support in all modern browsers
- **LocalStorage**: Universal support
- **Fallback**: Gracefully degrades to default theme if CSS variables aren't supported