import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button.tsx';
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { DATA_VISIBILITY } from '@/state/constants';
import { Input } from '@/components/ui/input';
import { TFormData } from '@/types/knowledge-base';

type INewBaseForm = {
    formValues?: TFormData;
    onSave: (f: TFormData) => void;
    onCancel?: () => void;
    isLoading?: boolean;
    isEditing?: boolean;
};

export function KnowledgeBaseForm({
    formValues,
    onSave,
    onCancel = () => {},
    isLoading = false,
    isEditing = false,
}: INewBaseForm) {
    const [name, setName] = useState(formValues?.name || '');
    const [description, setDescription] = useState(formValues?.description || '');
    const [isPublic, setIsPublic] = useState(formValues?.is_public || false);

    // Update form state when formValues prop changes
    useEffect(() => {
        if (formValues) {
            setName(formValues.name || '');
            setDescription(formValues.description || '');
            setIsPublic(formValues.is_public || false);
        }
    }, [formValues]);

    const handleSave = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({
            name,
            description,
            is_public: isPublic,
        });
    };
    return (
        <form onSubmit={handleSave} className="flex gap-4 flex-col">
            <Label className="mt-4">
                <span className="text-sm font-medium">What are you working on?</span>
            </Label>
            <Input
                data-testid="name-input"
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                required
                className="w-full dark:bg-accent focus-visible:ring-0 focus-visible:ring-offset-0"
            />
            <Label className="mt-4">
                <span className="text-sm font-medium">What are you trying to achieve?</span>
            </Label>
            <Textarea
                data-testid="description-textarea"
                value={description}
                className="w-full dark:bg-accent focus-visible:border-ring focus-visible:ring-0 focus-visible:ring-offset-0"
                onChange={e => setDescription(e.target.value)}
                rows={3}
            />

            <Label className="mt-4">
                <span className="text-sm font-medium">Visibility</span>
            </Label>
            <RadioGroup
                value={isPublic ? DATA_VISIBILITY.PUBLIC : DATA_VISIBILITY.PRIVATE}
                onValueChange={v => setIsPublic(v === DATA_VISIBILITY.PUBLIC)}
            >
                <div className="flex items-center space-x-2">
                    <RadioGroupItem
                        value={DATA_VISIBILITY.PUBLIC}
                        id="r1"
                        className="dark:bg-accent"
                    />
                    <div>
                        <Label
                            data-testid="datarobot-radio"
                            className="text-sm font-medium"
                            htmlFor="r1"
                        >
                            All app users
                        </Label>
                        <div className="text-sm text-gray-400">
                            Everyone with access to this app can view and use this forecast view
                        </div>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem
                        value={DATA_VISIBILITY.PRIVATE}
                        id="r2"
                        className="dark:bg-accent"
                    />
                    <div>
                        <Label
                            data-testid="private-radio"
                            className="text-sm font-medium"
                            htmlFor="r2"
                        >
                            Private
                        </Label>
                        <div className="text-sm text-gray-400">
                            Only you can view and use this forecast view
                        </div>
                    </div>
                </div>
            </RadioGroup>
            <div className="flex justify-end gap-4 mt-4">
                <Button
                    data-testid="cancel-button"
                    className="cursor-pointer"
                    variant="secondary"
                    onClick={onCancel}
                    type="button"
                    disabled={isLoading}
                >
                    Cancel
                </Button>
                <Button
                    data-testid="create-button"
                    className="cursor-pointer"
                    type="submit"
                    disabled={!name.trim() || isLoading}
                >
                    {isLoading
                        ? 'Saving...'
                        : isEditing
                          ? 'Update forecast view'
                          : 'Create forecast view'}
                </Button>
            </div>
        </form>
    );
}
