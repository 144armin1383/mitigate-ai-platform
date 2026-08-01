<?php

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Register MITIGATE REST API routes.
 */
add_action('rest_api_init', function () {

    register_rest_route('mitigate/v1', '/health', [
        'methods'             => 'GET',
        'callback'            => 'mitigate_api_health',
        'permission_callback' => '__return_true',
    ]);

});

/**
 * Health endpoint.
 */
function mitigate_api_health(): WP_REST_Response
{
    return new WP_REST_Response([
        'success'   => true,
        'platform'  => 'MITIGATE',
        'version'   => '1.0.0',
        'timestamp' => current_time('mysql'),
    ], 200);
}
