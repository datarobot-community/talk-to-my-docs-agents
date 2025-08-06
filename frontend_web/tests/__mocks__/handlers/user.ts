import { http, HttpResponse } from 'msw';

export const userHandlers = [
    http.get('api/v1/user', () => {
        return HttpResponse.json({
            uuid: '4aaa178b-ebbb-tttt-a1ff-71106123abce',
            email: 'test-ttmd@datarobot.com',
            first_name: 'Test',
            last_name: 'Unit',
            profile_image_url: null,
            identities: [
                {
                    uuid: 'ab69c8ed-ebbb-tttt-aaaa-71106123abce',
                    type: 'datarobot',
                    provider_id: 'datarobot_user',
                    provider_type: 'datarobot_user',
                    provider_user_id: '63dbc111e7411118dd1111f1',
                    provider_identity_id: null,
                },
            ],
        });
    }),
];
