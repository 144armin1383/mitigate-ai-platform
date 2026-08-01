<?php

if (!defined('ABSPATH')) {
    exit;
}

add_action('admin_menu', function () {
    add_menu_page(
        'MITIGATE',
        'MITIGATE',
        'manage_options',
        'mitigate-dashboard',
        'mitigate_render_admin_dashboard',
        'dashicons-admin-generic',
        3
    );
});

function mitigate_render_admin_dashboard(): void
{
    if (!current_user_can('manage_options')) {
        return;
    }

    echo '<div class="wrap">';
    echo '<h1>MITIGATE Control Centre</h1>';
    echo '<p>The AI management, automation, SEO, product import and technical tools will be managed from this area.</p>';
    echo '</div>';
}
