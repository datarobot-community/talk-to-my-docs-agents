import { MessagesSquare, LibraryBig, UserRound, Settings } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useMemo } from 'react';
import { useTheme } from '@/theme/theme-provider';
import drLogoDark from '@/assets/DataRobot_black.svg';
import drLogoLight from '@/assets/DataRobot_white.svg';
import drIcon from '@/assets/DataRobotLogo_black.svg';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarMenu,
    SidebarMenuItem,
    SidebarMenuButton,
    SidebarHeader,
    SidebarGroup,
} from '@/components/ui/sidebar';
import { useSidebar } from '@/hooks';
import { ROUTES } from '@/pages/routes';
import { Separator } from '@/components/ui/separator';

import { Link } from 'react-router-dom';
import { useCurrentUser } from '@/api/auth/hooks';
import { PATHS } from '@/constants/paths';
import { ChatList } from '@/components/custom/chat-list';
import { useTranslation } from '@/lib/i18n';

export function AppSidebar() {
    const { t } = useTranslation();
    const { open } = useSidebar();
    const { data: currentUser } = useCurrentUser();
    const location = useLocation();
    const { theme } = useTheme();

    // Menu items.
    const items = useMemo(
        () => [
            {
                title: t('Chat'),
                url: PATHS.CHAT,
                icon: MessagesSquare,
            },
            {
                title: t('Knowledge Bases'),
                url: ROUTES.KNOWLEDGE_BASES,
                icon: LibraryBig,
            },
            {
                title: t('App Settings'),
                url: ROUTES.SETTINGS,
                icon: Settings,
            },
            // {
            //     title: t('Assistants'),
            //     url: PATHS.CHAT,
            //     icon: Brain,
            // },
            // {
            //     title: t('Search'),
            //     url: PATHS.CHAT,
            //     icon: Search,
            // },
        ],
        [t]
    );

    return (
        <Sidebar collapsible="icon" className="bg-background" data-testid="app-sidebar">
            <SidebarHeader className="h-15 border-b">
                {open ? (
                    <Link to={PATHS.CHAT} className="flex items-center py-1">
                        <img
                            src={theme === 'dark' ? drLogoLight : drLogoDark}
                            alt="DataRobot"
                            className="w-[130px]"
                        />
                    </Link>
                ) : (
                    <Link to={PATHS.CHAT} className="ml-2 inline-block py-3">
                        <img src={drIcon} alt="DataRobot" className="w-[20px]" />
                    </Link>
                )}
            </SidebarHeader>
            <SidebarContent className="pl-1">
                <SidebarMenu>
                    <SidebarGroup className="gap-2">
                        {items.map(item => (
                            <SidebarMenuItem key={item.title}>
                                <SidebarMenuButton
                                    asChild
                                    isActive={
                                        location.pathname === item.url ||
                                        (item.url === ROUTES.KNOWLEDGE_BASES &&
                                            location.pathname.startsWith(PATHS.KNOWLEDGE_BASES))
                                    }
                                >
                                    <Link to={item.url}>
                                        <item.icon />
                                        <span>{item.title}</span>
                                    </Link>
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                        ))}
                        <Separator className="my-4 border-t" />
                        {open && (
                            <>
                                <p className="ml-1 text-base font-semibold">{t('Chats')}</p>
                                <SidebarMenuItem>
                                    <SidebarMenuButton asChild>
                                        <ChatList />
                                    </SidebarMenuButton>
                                </SidebarMenuItem>
                            </>
                        )}
                    </SidebarGroup>
                </SidebarMenu>
            </SidebarContent>
            <SidebarFooter>
                <div className="mb-2.5 ml-0.5 flex h-9 w-full items-center gap-1">
                    <Avatar>
                        <AvatarFallback>
                            {currentUser && currentUser.first_name && currentUser.last_name ? (
                                `${currentUser.first_name[0]}${currentUser.last_name[0]}`
                            ) : (
                                <UserRound />
                            )}
                        </AvatarFallback>
                    </Avatar>
                    {open && (
                        <span>
                            {(() => {
                                const displayName =
                                    currentUser && currentUser.first_name && currentUser.last_name
                                        ? `${currentUser.first_name} ${currentUser.last_name}`
                                        : currentUser?.email || t('User');
                                return displayName.length > 20
                                    ? `${displayName.slice(0, 20)}...`
                                    : displayName;
                            })()}
                        </span>
                    )}
                </div>
            </SidebarFooter>
        </Sidebar>
    );
}
