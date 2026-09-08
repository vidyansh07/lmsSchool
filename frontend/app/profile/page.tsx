'use client';

import { RequireAuth } from '@/components/require-auth';
import { StudentProfileForm } from './student-profile-form';
import { TrainerProfileForm } from './trainer-profile-form';
import { AccountDetailsForm } from './account-details-form';
import { useAuth } from '@/components/auth-provider';
import { ProfileImageField } from '@/components/profile-image-field';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

function ProfileContent() {
  const { user } = useAuth();

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My profile</h1>
        <p className="text-sm text-muted-foreground">
          Update your contact details and the information your trainers and administrators can see.
        </p>
      </div>

      <Card className="animate-rise-in">
        <CardHeader>
          <CardTitle>Photo</CardTitle>
          <CardDescription>Shown next to your name across the platform.</CardDescription>
        </CardHeader>
        <CardContent>
          <ProfileImageField />
        </CardContent>
      </Card>

      <AccountDetailsForm />

      {user?.profile_type === 'student' ? <StudentProfileForm /> : null}
      {user?.profile_type === 'trainer' ? <TrainerProfileForm /> : null}
    </div>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileContent />
    </RequireAuth>
  );
}
