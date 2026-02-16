import axios from 'axios';
import axiosRetry from 'axios-retry';

import { getApiUrl } from '@/lib/utils';

const baseApiUrl = getApiUrl();

const apiClient = axios.create({
    baseURL: baseApiUrl,
    headers: {
        Accept: 'application/json',
        'Content-type': 'application/json',
    },
    withCredentials: true,
});

axiosRetry(apiClient, {
    retries: 5,
    retryDelay: axiosRetry.exponentialDelay,
});

export default apiClient;
