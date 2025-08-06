export const chatKeys = {
    all: ['chats'],
    chatList: () => [...chatKeys.all, 'list'],
    messages: (chatId: string = '') => [...chatKeys.all, chatId],
    llmCatalog: ['llmCatalog'],
};
