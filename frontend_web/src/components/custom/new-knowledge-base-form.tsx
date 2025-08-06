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
};

export function NewBaseForm({
    formValues,
    onSave,
    onCancel = () => {},
    isLoading = false,
}: INewBaseForm) {
    const [name, setName] = useState(formValues?.name || '');
    const [description, setDescription] = useState(formValues?.description || '');
    const [visibility, setVisibility] = useState(
        formValues?.visibility || DATA_VISIBILITY.DATAROBOT
    );

    // Update form state when formValues prop changes
    useEffect(() => {
        if (formValues) {
            setName(formValues.name || '');
            setDescription(formValues.description || '');
            setVisibility(formValues.visibility || DATA_VISIBILITY.DATAROBOT);
        }
    }, [formValues]);

    const handleSave = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({
            name,
            description,
            visibility,
        });
    };
    return (
        <form onSubmit={handleSave} className="flex gap-4 flex-col">
            <Label className="mt-4">
                <span className="text-sm font-medium">What are you working on?</span>
            </Label>
            <Input
                test-id="name-input"
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                required
                className="w-full"
            />
            <Label className="mt-4">
                <span className="text-sm font-medium">What are you trying to achieve?</span>
            </Label>
            <Textarea
                test-id="description-textarea"
                value={description}
                className="w-full"
                onChange={e => setDescription(e.target.value)}
                rows={3}
            />

            <Label className="mt-4">
                <span className="text-sm font-medium">Visibility</span>
            </Label>
            <RadioGroup value={visibility} onValueChange={setVisibility}>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value={DATA_VISIBILITY.DATAROBOT} id="r1" />
                    <div>
                        <Label
                            test-id="datarobot-radio"
                            className="text-sm font-medium"
                            htmlFor="r1"
                        >
                            DataRobot
                        </Label>
                        <div className="text-sm text-gray-400">
                            Everyone in your organization can view and use this knowledge base
                        </div>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value={DATA_VISIBILITY.PRIVATE} id="r2" />
                    <div>
                        <Label test-id="private-radio" className="text-sm font-medium" htmlFor="r2">
                            Private
                        </Label>
                        <div className="text-sm text-gray-400">
                            Only you can view and use this knowledge base
                        </div>
                    </div>
                </div>
            </RadioGroup>
            <div className="flex justify-end gap-4 mt-4">
                <Button
                    test-id="cancel-button"
                    className="cursor-pointer"
                    variant="secondary"
                    onClick={onCancel}
                    type="button"
                    disabled={isLoading}
                >
                    Cancel
                </Button>
                <Button
                    test-id="create-button"
                    className="cursor-pointer"
                    type="submit"
                    disabled={!name.trim() || isLoading}
                >
                    {isLoading ? 'Saving...' : 'Create knowledge base'}
                </Button>
            </div>
        </form>
    );
}
