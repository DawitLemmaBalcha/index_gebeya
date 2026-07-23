import { API_BASE_URL } from '../config';

const SESSION_KEY = 'index_session_id';
const USER_ID_KEY = 'index_user_id';

// Simple UUID generator since we can't install packages easily
const generateUUID = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

export const getAnalyticsHeaders = () => {
    let sessionId = localStorage.getItem(SESSION_KEY);
    if (!sessionId) {
        sessionId = generateUUID();
        localStorage.setItem(SESSION_KEY, sessionId);
    }

    const headers = {
        'x-session-id': sessionId,
    };

    const userId = localStorage.getItem(USER_ID_KEY);
    if (userId) {
        headers['x-user-id'] = userId;
    }

    return headers;
};

export const logEvent = async (eventType, itemId = null, metaData = null) => {
    const headers = getAnalyticsHeaders();
    
    try {
        // RENAMED TO /activity TO BYPASS AD BLOCKERS
        await fetch(`${API_BASE_URL}/activity/events`, {
            method: 'POST',
            headers: {
                ...headers,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                event_type: eventType,
                item_id: itemId,
                meta_data: metaData
            })
        });
    } catch (e) {
        console.warn("Analytics logging failed", e);
    }
};