import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button.tsx';
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { DATA_VISIBILITY } from '@/state/constants';
import { Input } from '@/components/ui/input';
import { TFormData } from '@/types';
import { useTranslation } from '@/lib/i18n';
import { isVdbEnabled } from '@/lib/ttmdocs-utils';

type INewBaseForm = {
    formValues?: TFormData;
    onSave: (f: TFormData) => void;
    onCancel?: () => void;
    isLoading?: boolean;
    isEditing?: boolean;
};

const MAX_NAME_CHARS = 255;
const MAX_DESCRIPTION_CHARS = 1000;

export function KnowledgeBaseForm({
    formValues,
    onSave,
    onCancel = () => {},
    isLoading = false,
    isEditing = false,
}: INewBaseForm) {
    const { t } = useTranslation();
    // Semantic-search feature availability (injected by the backend via window.ENV).
    const vdbEnabled = isVdbEnabled();
    const [name, setName] = useState(formValues?.name || '');
    const [description, setDescription] = useState(formValues?.description || '');
    const [isPublic, setIsPublic] = useState(formValues?.is_public || false);
    // New KBs default to semantic when the feature is available; editing keeps the
    // KB's stored mode. When the feature is off, mode stays keyword (original).
    const [retrievalMode, setRetrievalMode] = useState(
        formValues?.retrieval_mode || (vdbEnabled ? 'semantic' : 'keyword')
    );

    // Update form state when formValues prop changes
    useEffect(() => {
        if (formValues) {
            setName(formValues.name || '');
            setDescription(formValues.description || '');
            setIsPublic(formValues.is_public || false);
            // Always sync the stored mode. A legacy KB with no retrieval_mode is
            // keyword by definition (the backend default), so fall back to
            // 'keyword' rather than leaving the 'semantic' mount default in place,
            // which would silently switch the KB and trigger unwanted indexing.
            setRetrievalMode(formValues.retrieval_mode || 'keyword');
        }
    }, [formValues]);

    const handleSave = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({
            name,
            description,
            is_public: isPublic,
            retrieval_mode: vdbEnabled ? retrievalMode : 'keyword',
        });
    };
    return (
        <form onSubmit={handleSave} className="flex flex-col gap-4">
            <Label className="mt-4 block">
                <span className="body">{t('What are you working on?')}</span>
                <span className="caption-01 ml-1">{t('(Required)')}</span>
            </Label>
            <div>
                <Input
                    data-testid="name-input"
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    required
                    maxLength={MAX_NAME_CHARS}
                    placeholder={t('Will be used as Knowledge Base name')}
                    className="w-full"
                />
                <div className="caption-01 mt-1 text-right">
                    ({name.length}/{MAX_NAME_CHARS} {t('characters')})
                </div>
            </div>

            <Label className="mt-4 block">
                <span className="body">{t('What are you trying to achieve?')}</span>
                <span className="caption-01 ml-1">{t('(Required)')}</span>
                <p className="body-secondary">
                    {t('A detailed description helps generate more accurate results.')}
                </p>
            </Label>
            <div>
                <Textarea
                    data-testid="description-textarea"
                    value={description}
                    required
                    placeholder={t('Additional context for the Knowledge Base')}
                    className="w-full pb-0"
                    onChange={e => setDescription(e.target.value)}
                    rows={3}
                    maxLength={MAX_DESCRIPTION_CHARS}
                />
                <div className="caption-01 mt-1 text-right">
                    ({description.length}/{MAX_DESCRIPTION_CHARS} {t('characters')})
                </div>
            </div>

            <Label className="mt-4">
                <span className="body">{t('Visibility')}</span>
            </Label>
            <RadioGroup
                value={isPublic ? DATA_VISIBILITY.PUBLIC : DATA_VISIBILITY.PRIVATE}
                onValueChange={v => setIsPublic(v === DATA_VISIBILITY.PUBLIC)}
            >
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value={DATA_VISIBILITY.PUBLIC} id="r1" />
                    <div>
                        <Label data-testid="datarobot-radio" className="body" htmlFor="r1">
                            {t('All app users')}
                        </Label>
                        <div className="body-secondary">
                            {t(
                                'Everyone with access to this app can view and use this knowledge base'
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value={DATA_VISIBILITY.PRIVATE} id="r2" />
                    <div>
                        <Label data-testid="private-radio" className="body" htmlFor="r2">
                            {t('Private')}
                        </Label>
                        <div className="body-secondary">
                            {t('Only you can view and use this knowledge base')}
                        </div>
                    </div>
                </div>
            </RadioGroup>
            {vdbEnabled && (
                <>
                    <Label className="mt-4">
                        <span className="body">{t('Search mode')}</span>
                    </Label>
                    <RadioGroup value={retrievalMode} onValueChange={v => setRetrievalMode(v)}>
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="semantic" id="rm-semantic" />
                            <div>
                                <Label
                                    data-testid="semantic-radio"
                                    className="body"
                                    htmlFor="rm-semantic"
                                >
                                    {t('Semantic search')}
                                </Label>
                                <div className="body-secondary">
                                    {t(
                                        'Smarter, meaning-based search over your documents (recommended). May take a moment to index after upload.'
                                    )}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="keyword" id="rm-keyword" />
                            <div>
                                <Label
                                    data-testid="keyword-radio"
                                    className="body"
                                    htmlFor="rm-keyword"
                                >
                                    {t('Keyword match')}
                                </Label>
                                <div className="body-secondary">
                                    {t(
                                        'Classic exact keyword matching over the full document text.'
                                    )}
                                </div>
                            </div>
                        </div>
                    </RadioGroup>
                </>
            )}
            <div className="mt-4 flex justify-end gap-4">
                <Button
                    data-testid="cancel-button"
                    className="cursor-pointer"
                    variant="secondary"
                    onClick={onCancel}
                    type="button"
                    disabled={isLoading}
                >
                    {t('Cancel')}
                </Button>
                <Button
                    data-testid="create-button"
                    className="cursor-pointer"
                    type="submit"
                    disabled={!name.trim() || !description.trim() || isLoading}
                >
                    {isLoading
                        ? t('Saving...')
                        : isEditing
                          ? t('Update knowledge base')
                          : t('Create knowledge base')}
                </Button>
            </div>
        </form>
    );
}
