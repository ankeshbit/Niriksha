import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { RootStackParamList } from './types';

// Screens
import { LoginScreen } from '../screens/LoginScreen';
import { DashboardScreen } from '../screens/DashboardScreen';
import { NewInspectionScreen } from '../screens/NewInspectionScreen';
import { CaptureImagesScreen } from '../screens/CaptureImagesScreen';
import { AnalyzingScreen } from '../screens/AnalyzingScreen';
import { ExtractedDeclarationsScreen } from '../screens/ExtractedDeclarationsScreen';
import { FindingsScreen } from '../screens/FindingsScreen';
import { EvidenceReviewScreen } from '../screens/EvidenceReviewScreen';
import { ReviewAndSubmitScreen } from '../screens/ReviewAndSubmitScreen';
import { ReportPreviewScreen } from '../screens/ReportPreviewScreen';
import { ReportsListScreen } from '../screens/ReportsListScreen';
import { ProfileScreen } from '../screens/ProfileScreen';
import { DraftOfflineScreen } from '../screens/DraftOfflineScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();

export const AppNavigator: React.FC = () => {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Login"
        screenOptions={{
          headerShown: false,
          animation: 'fade',
        }}
      >
        <Stack.Screen name="Login" component={LoginScreen} />
        <Stack.Screen name="Dashboard" component={DashboardScreen} />
        <Stack.Screen name="NewInspection" component={NewInspectionScreen} />
        <Stack.Screen name="CaptureImages" component={CaptureImagesScreen} />
        <Stack.Screen name="Analyzing" component={AnalyzingScreen} />
        <Stack.Screen name="ExtractedDeclarations" component={ExtractedDeclarationsScreen} />
        <Stack.Screen name="Findings" component={FindingsScreen} />
        <Stack.Screen name="EvidenceReview" component={EvidenceReviewScreen} />
        <Stack.Screen name="ReviewAndSubmit" component={ReviewAndSubmitScreen} />
        <Stack.Screen name="ReportPreview" component={ReportPreviewScreen} />
        <Stack.Screen name="ReportsList" component={ReportsListScreen} />
        <Stack.Screen name="Profile" component={ProfileScreen} />
        <Stack.Screen name="DraftOffline" component={DraftOfflineScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
};
