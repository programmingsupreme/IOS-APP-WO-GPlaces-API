import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Platform,
  AppState,
  AppStateStatus,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { FlashList } from '@shopify/flash-list';
import * as Location from 'expo-location';
import axios from 'axios';
import { Ionicons } from '@expo/vector-icons';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface GasStation {
  id: string;
  place_id: string;
  name: string;
  address: string | null;
  latitude: number;
  longitude: number;
  distance_miles: number;
  gas_price: number | null;
  gas_price_formatted: string | null;
  diesel_price: number | null;
  diesel_price_formatted: string | null;
}

interface LocationCoords {
  latitude: number;
  longitude: number;
}

export default function Index() {
  const [fuelType, setFuelType] = useState<'gas' | 'diesel'>('gas');
  const [stations, setStations] = useState<GasStation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState<LocationCoords | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [showPaywall, setShowPaywall] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);

  // Request location permission and get current location
  const getLocation = useCallback(async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        // For web preview, use a default location (New York City)
        if (Platform.OS === 'web') {
          console.log('Using default location for web preview');
          const defaultCoords = {
            latitude: 40.7128,
            longitude: -74.0060,
          };
          setLocation(defaultCoords);
          setLocationError(null);
          return defaultCoords;
        }
        setLocationError('Location permission denied. Please enable location access.');
        setLoading(false);
        return null;
      }

      const currentLocation = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      const coords = {
        latitude: currentLocation.coords.latitude,
        longitude: currentLocation.coords.longitude,
      };
      setLocation(coords);
      setLocationError(null);
      return coords;
    } catch (err) {
      console.error('Location error:', err);
      // For web preview, use a default location (New York City)
      if (Platform.OS === 'web') {
        console.log('Using default location for web preview after error');
        const defaultCoords = {
          latitude: 40.7128,
          longitude: -74.0060,
        };
        setLocation(defaultCoords);
        setLocationError(null);
        return defaultCoords;
      }
      setLocationError('Unable to get your location. Please try again.');
      setLoading(false);
      return null;
    }
  }, []);

  // Fetch stations from backend
  const fetchStations = useCallback(async (coords: LocationCoords, fuel: 'gas' | 'diesel') => {
    try {
      setError(null);
      const response = await axios.get(`${BACKEND_URL}/api/stations`, {
        params: {
          latitude: coords.latitude,
          longitude: coords.longitude,
          fuel_type: fuel,
        },
        timeout: 30000,
      });
      setStations(response.data.stations || []);
    } catch (err: any) {
      console.error('Fetch error:', err);
      setError(err.response?.data?.detail || 'Unable to fetch gas stations. Please try again.');
      setStations([]);
    }
  }, []);

  // Load data
  const loadData = useCallback(async (showLoader = true) => {
    if (showLoader) setLoading(true);
    
    let coords = location;
    if (!coords) {
      coords = await getLocation();
    }
    
    if (coords) {
      await fetchStations(coords, fuelType);
    }
    
    setLoading(false);
    setRefreshing(false);
  }, [location, fuelType, getLocation, fetchStations]);

  // Initial load
  useEffect(() => {
    loadData();
  }, []);

  // Reload when fuel type changes
  useEffect(() => {
    if (location) {
      loadData(false);
    }
  }, [fuelType]);

  // Handle app state changes (refresh when coming to foreground)
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextAppState: AppStateStatus) => {
      if (nextAppState === 'active' && location) {
        loadData(false);
      }
    });

    return () => {
      subscription.remove();
    };
  }, [location, loadData]);

  // Pull to refresh
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    // Get fresh location on refresh
    const coords = await getLocation();
    if (coords) {
      await fetchStations(coords, fuelType);
    }
    setRefreshing(false);
  }, [fuelType, getLocation, fetchStations]);

  // Toggle fuel type
  const toggleFuelType = (type: 'gas' | 'diesel') => {
    setFuelType(type);
  };

  // Handle subscription (mock)
  const handleSubscribe = () => {
    setIsSubscribed(true);
    setShowPaywall(false);
  };

  // Render station item
  const renderStation = ({ item, index }: { item: GasStation; index: number }) => {
    const price = fuelType === 'gas' ? item.gas_price_formatted : item.diesel_price_formatted;
    const hasPrice = price !== null;
    const rank = index + 1;

    return (
      <View style={styles.stationCard}>
        <View style={styles.rankContainer}>
          <Text style={styles.rankText}>#{rank}</Text>
        </View>
        
        <View style={styles.fuelIconContainer}>
          <Ionicons 
            name={fuelType === 'gas' ? 'car' : 'bus'} 
            size={28} 
            color={fuelType === 'gas' ? '#4CAF50' : '#FF9800'} 
          />
          <Text style={styles.fuelTypeLabel}>
            {fuelType === 'gas' ? 'GAS' : 'DIESEL'}
          </Text>
        </View>
        
        <View style={styles.stationInfo}>
          <Text style={styles.stationName} numberOfLines={1}>
            {item.name}
          </Text>
          <Text style={styles.stationAddress} numberOfLines={1}>
            {item.address || 'Address not available'}
          </Text>
        </View>
        
        <View style={styles.priceDistanceContainer}>
          <Text style={[styles.priceText, !hasPrice && styles.noPriceText]}>
            {hasPrice ? price : 'N/A'}
          </Text>
          <Text style={styles.perGallon}>{hasPrice ? '/gal' : ''}</Text>
          <View style={styles.distanceRow}>
            <Ionicons name="location-outline" size={14} color="#888" />
            <Text style={styles.distanceText}>{item.distance_miles} mi</Text>
          </View>
        </View>
      </View>
    );
  };

  // Paywall Modal
  if (showPaywall && !isSubscribed) {
    return (
      <SafeAreaView style={styles.paywallContainer}>
        <View style={styles.paywallContent}>
          <Ionicons name="flash" size={80} color="#4CAF50" />
          <Text style={styles.paywallTitle}>Fuel Finder Pro</Text>
          <Text style={styles.paywallSubtitle}>Unlock unlimited access to real-time fuel prices</Text>
          
          <View style={styles.featureList}>
            <View style={styles.featureItem}>
              <Ionicons name="checkmark-circle" size={24} color="#4CAF50" />
              <Text style={styles.featureText}>Real-time gas & diesel prices</Text>
            </View>
            <View style={styles.featureItem}>
              <Ionicons name="checkmark-circle" size={24} color="#4CAF50" />
              <Text style={styles.featureText}>Find closest 10 stations</Text>
            </View>
            <View style={styles.featureItem}>
              <Ionicons name="checkmark-circle" size={24} color="#4CAF50" />
              <Text style={styles.featureText}>Auto-updates as you drive</Text>
            </View>
          </View>
          
          <View style={styles.priceBox}>
            <Text style={styles.trialText}>1 WEEK FREE TRIAL</Text>
            <Text style={styles.subscriptionPrice}>$5.99/week</Text>
            <Text style={styles.cancelText}>Cancel anytime</Text>
          </View>
          
          <TouchableOpacity style={styles.subscribeButton} onPress={handleSubscribe}>
            <Text style={styles.subscribeButtonText}>Start Free Trial</Text>
          </TouchableOpacity>
          
          <TouchableOpacity onPress={() => setShowPaywall(false)}>
            <Text style={styles.skipText}>Maybe Later</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Fuel Finder</Text>
        <TouchableOpacity 
          style={styles.starButton}
          onPress={() => setShowPaywall(true)}
          accessibilityLabel="Subscription"
        >
          <Ionicons 
            name={isSubscribed ? "star" : "star-outline"} 
            size={24} 
            color={isSubscribed ? "#FFD700" : "#888"} 
          />
        </TouchableOpacity>
      </View>

      {/* Fuel Type Toggle */}
      <View style={styles.toggleContainer}>
        <TouchableOpacity
          style={[
            styles.toggleButton,
            fuelType === 'gas' && styles.toggleButtonActive,
          ]}
          onPress={() => toggleFuelType('gas')}
        >
          <Ionicons 
            name="car" 
            size={20} 
            color={fuelType === 'gas' ? '#fff' : '#888'} 
          />
          <Text style={[
            styles.toggleText,
            fuelType === 'gas' && styles.toggleTextActive,
          ]}>Gas</Text>
        </TouchableOpacity>
        
        <TouchableOpacity
          style={[
            styles.toggleButton,
            fuelType === 'diesel' && styles.toggleButtonActive,
            fuelType === 'diesel' && styles.toggleButtonDiesel,
          ]}
          onPress={() => toggleFuelType('diesel')}
        >
          <Ionicons 
            name="bus" 
            size={20} 
            color={fuelType === 'diesel' ? '#fff' : '#888'} 
          />
          <Text style={[
            styles.toggleText,
            fuelType === 'diesel' && styles.toggleTextActive,
          ]}>Diesel</Text>
        </TouchableOpacity>
      </View>

      {/* Location Status */}
      {location && (
        <View style={styles.locationBar}>
          <Ionicons name="navigate" size={16} color="#4CAF50" />
          <Text style={styles.locationText}>Showing stations near you</Text>
        </View>
      )}

      {/* Content */}
      {loading ? (
        <View style={styles.centerContent}>
          <ActivityIndicator size="large" color="#4CAF50" />
          <Text style={styles.loadingText}>Finding nearby stations...</Text>
        </View>
      ) : locationError ? (
        <View style={styles.centerContent}>
          <Ionicons name="location-outline" size={60} color="#888" />
          <Text style={styles.errorText}>{locationError}</Text>
          <TouchableOpacity style={styles.retryButton} onPress={() => loadData()}>
            <Text style={styles.retryButtonText}>Enable Location</Text>
          </TouchableOpacity>
        </View>
      ) : error ? (
        <View style={styles.centerContent}>
          <Ionicons name="alert-circle-outline" size={60} color="#FF5722" />
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryButton} onPress={() => loadData()}>
            <Text style={styles.retryButtonText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : stations.length === 0 ? (
        <View style={styles.centerContent}>
          <Ionicons name="car-outline" size={60} color="#888" />
          <Text style={styles.emptyText}>No gas stations found nearby</Text>
          <TouchableOpacity style={styles.retryButton} onPress={() => loadData()}>
            <Text style={styles.retryButtonText}>Search Again</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlashList
          data={stations}
          renderItem={renderStation}
          estimatedItemSize={100}
          keyExtractor={(item) => item.place_id}
          contentContainerStyle={styles.listContainer}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#4CAF50"
              colors={['#4CAF50']}
            />
          }
          ListHeaderComponent={
            <Text style={styles.listHeader}>
              Top 10 Cheapest {fuelType === 'gas' ? 'Gas' : 'Diesel'} Stations
            </Text>
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#2a2a2a',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
  },
  starButton: {
    padding: 8,
    marginRight: -8,
  },
  toggleContainer: {
    flexDirection: 'row',
    marginHorizontal: 20,
    marginVertical: 16,
    backgroundColor: '#1e1e1e',
    borderRadius: 12,
    padding: 4,
  },
  toggleButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 10,
    gap: 8,
  },
  toggleButtonActive: {
    backgroundColor: '#4CAF50',
  },
  toggleButtonDiesel: {
    backgroundColor: '#FF9800',
  },
  toggleText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#888',
  },
  toggleTextActive: {
    color: '#fff',
  },
  locationBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    gap: 6,
    backgroundColor: 'rgba(76, 175, 80, 0.1)',
  },
  locationText: {
    fontSize: 13,
    color: '#4CAF50',
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  loadingText: {
    marginTop: 16,
    fontSize: 16,
    color: '#888',
  },
  errorText: {
    marginTop: 16,
    fontSize: 16,
    color: '#888',
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  emptyText: {
    marginTop: 16,
    fontSize: 16,
    color: '#888',
  },
  retryButton: {
    marginTop: 20,
    paddingHorizontal: 24,
    paddingVertical: 12,
    backgroundColor: '#4CAF50',
    borderRadius: 8,
  },
  retryButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  listContainer: {
    paddingHorizontal: 16,
    paddingBottom: 20,
  },
  listHeader: {
    fontSize: 14,
    color: '#888',
    marginBottom: 12,
    marginTop: 8,
  },
  stationCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1e1e1e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  rankContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#2a2a2a',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  rankText: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#fff',
  },
  fuelIconContainer: {
    alignItems: 'center',
    marginRight: 12,
    width: 40,
  },
  fuelTypeLabel: {
    fontSize: 9,
    color: '#888',
    marginTop: 2,
    fontWeight: '600',
  },
  stationInfo: {
    flex: 1,
    marginRight: 12,
  },
  stationName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 4,
  },
  stationAddress: {
    fontSize: 12,
    color: '#888',
  },
  priceDistanceContainer: {
    alignItems: 'flex-end',
  },
  priceText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#4CAF50',
  },
  noPriceText: {
    color: '#888',
    fontSize: 16,
  },
  perGallon: {
    fontSize: 11,
    color: '#888',
    marginTop: -2,
  },
  distanceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    gap: 2,
  },
  distanceText: {
    fontSize: 12,
    color: '#888',
  },
  // Paywall styles
  paywallContainer: {
    flex: 1,
    backgroundColor: '#121212',
  },
  paywallContent: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 30,
  },
  paywallTitle: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
    marginTop: 20,
  },
  paywallSubtitle: {
    fontSize: 16,
    color: '#888',
    textAlign: 'center',
    marginTop: 10,
    marginBottom: 30,
  },
  featureList: {
    width: '100%',
    marginBottom: 30,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16,
  },
  featureText: {
    fontSize: 16,
    color: '#fff',
  },
  priceBox: {
    backgroundColor: '#1e1e1e',
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
    width: '100%',
    marginBottom: 20,
  },
  trialText: {
    fontSize: 14,
    color: '#4CAF50',
    fontWeight: '600',
    marginBottom: 8,
  },
  subscriptionPrice: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#fff',
  },
  cancelText: {
    fontSize: 13,
    color: '#888',
    marginTop: 4,
  },
  subscribeButton: {
    backgroundColor: '#4CAF50',
    paddingHorizontal: 60,
    paddingVertical: 16,
    borderRadius: 30,
    marginBottom: 16,
  },
  subscribeButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
  },
  skipText: {
    fontSize: 16,
    color: '#888',
    marginTop: 10,
  },
});
